"""Package set models, AXML split detector, and integrity validation engine.

PT-MOB-102 (Issue #70): Validates base APK presence, package homogeneity,
version code consistency, split name uniqueness, SHA-256 digests, and size quotas.
"""

from __future__ import annotations

import hashlib
import io
import re
import stat
import sys
from enum import StrEnum
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from pydantic import Field, model_validator

from .models import Model

# Constants
MAX_FILE_SIZE = 150 * 1024 * 1024  # 150 MiB per file
MAX_PACKAGE_SET_SIZE = 150 * 1024 * 1024  # 150 MiB cumulative set limit
MAX_ZIP_ENTRIES = 20000
MAX_EXPANDED_ZIP = 512 * 1024 * 1024
MAX_SINGLE_ZIP_ENTRY = 128 * 1024 * 1024
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
SPLIT_NAME_PATTERN = r"^[a-zA-Z0-9_.-]+$"
SPLIT_NAME_REGEX = re.compile(SPLIT_NAME_PATTERN)
RESERVED_SPLIT_NAMES = frozenset({"base"})


def directory_digest(directory):
    """Bind names and bytes without parsing untrusted APK structures on the host."""
    entries = [
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(directory.iterdir())
    ]
    import json

    return hashlib.sha256(json.dumps(entries, ensure_ascii=True).encode()).hexdigest()


class PackageSetIntegrityError(Exception):
    """Integrity rejection mapped cleanly to 4xx HTTP responses."""

    def __init__(self, code: str, detail: str = "", http_status: int = 400):
        if not detail:
            detail = f"Package set integrity error: {code}"
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.http_status = http_status


class PackagePart(StrEnum):
    BASE = "BASE"
    SPLIT = "SPLIT"


class PackageFile(Model):
    file_name: str = Field(min_length=1, max_length=255)
    part: PackagePart
    split_name: str | None = Field(
        default=None, max_length=255, pattern=SPLIT_NAME_PATTERN
    )
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    package_name: str = Field(min_length=1, max_length=200)
    version_code: int = Field(ge=0, strict=True)
    version_name: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_part_split_invariant(self) -> PackageFile:
        if self.part == PackagePart.BASE and self.split_name is not None:
            raise ValueError("BASE package must have split_name=None")
        if self.part == PackagePart.SPLIT:
            if not self.split_name or not self.split_name.strip():
                raise ValueError("SPLIT package must have non-empty split_name")
            if self.split_name.strip().lower() in RESERVED_SPLIT_NAMES:
                raise ValueError("SPLIT package cannot declare reserved split name 'base'")
            if not SPLIT_NAME_REGEX.fullmatch(self.split_name):
                msg = (
                    f"SPLIT package split_name '{self.split_name}' "
                    f"must match '{SPLIT_NAME_PATTERN}'"
                )
                raise ValueError(msg)
        return self


class PackageSet(Model):
    package_name: str = Field(min_length=1, max_length=200)
    version_code: int = Field(ge=0, strict=True)
    version_name: str | None = Field(default=None, max_length=1024)
    base: PackageFile
    splits: list[PackageFile] = Field(default_factory=list, max_length=100)
    total_size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_set_invariants(self) -> PackageSet:
        if self.base.part != PackagePart.BASE:
            raise ValueError("base file must have part=BASE")
        if self.base.package_name != self.package_name:
            raise ValueError("base package_name does not match package set")
        if self.base.version_code != self.version_code:
            raise ValueError("base version_code does not match package set")
        seen_splits = set()
        for split in self.splits:
            if split.part != PackagePart.SPLIT:
                raise ValueError(f"split file '{split.file_name}' must have part=SPLIT")
            if split.package_name != self.package_name:
                raise ValueError(f"split '{split.file_name}' package_name mismatch")
            if split.version_code != self.version_code:
                raise ValueError(f"split '{split.file_name}' version_code mismatch")
            if not split.split_name or split.split_name in seen_splits:
                raise ValueError(f"duplicate or invalid split name '{split.split_name}'")
            if split.split_name.strip().lower() in RESERVED_SPLIT_NAMES:
                raise ValueError("split cannot declare reserved split name 'base'")
            if not SPLIT_NAME_REGEX.fullmatch(split.split_name):
                raise ValueError(f"split name '{split.split_name}' contains invalid characters")
            seen_splits.add(split.split_name)
        expected_size = self.base.size_bytes + sum(s.size_bytes for s in self.splits)
        if self.total_size_bytes != expected_size:
            raise ValueError(
                f"total_size_bytes {self.total_size_bytes} != computed sum {expected_size}"
            )
        return self

    @property
    def all_files(self) -> list[PackageFile]:
        return [self.base, *self.splits]

    @property
    def file_map(self) -> dict[str, PackageFile]:
        return {f.file_name: f for f in self.all_files}


class PackageSetManifestInput(Model):
    package_name: str = Field(min_length=1, max_length=200)
    version_code: int = Field(ge=0, strict=True)
    version_name: str | None = Field(default=None, max_length=1024)
    files: list[PackageFile] = Field(min_length=1, max_length=101)


def inspect_axml(manifest_bytes: bytes) -> tuple[str, int, str | None, str | None]:
    """Inspect binary AndroidManifest.xml and extract metadata.

    Returns:
        (package_name, version_code, version_name, split_name)
        split_name is None for base APK, or non-empty string for split APK.
    Raises:
        PackageSetIntegrityError: if manifest is corrupted, missing, or invalid.
    """
    from androguard.core.axml import AXMLPrinter
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    try:
        printer = AXMLPrinter(manifest_bytes)
        root = printer.get_xml_obj()
    except Exception as exc:
        raise PackageSetIntegrityError(
            "CORRUPTED_FILE", f"Binary AndroidManifest.xml could not be parsed: {exc}"
        ) from exc

    if root is None or root.tag != "manifest":
        raise PackageSetIntegrityError(
            "CORRUPTED_FILE", "Binary Android manifest root is not <manifest>"
        )

    # 1. Package Name
    package_name = root.get("package")
    if not package_name or not isinstance(package_name, str) or not package_name.strip():
        raise PackageSetIntegrityError("CORRUPTED_FILE", "Manifest package is missing or empty")
    package_name = package_name.strip()

    # 2. Version Code
    raw_code = root.get(ANDROID_NS + "versionCode")
    if raw_code is None:
        raise PackageSetIntegrityError("CORRUPTED_FILE", "Manifest versionCode is missing")
    try:
        if isinstance(raw_code, str):
            raw_code = raw_code.strip()
            version_code = int(raw_code, 16 if raw_code.lower().startswith("0x") else 10)
        else:
            version_code = int(raw_code)
        if not 0 <= version_code <= 0x7FFFFFFF:
            raise ValueError("versionCode outside supported range 0..2147483647")
    except (TypeError, ValueError) as exc:
        raise PackageSetIntegrityError(
            "CORRUPTED_FILE", f"Manifest versionCode must be an integer in 0..2147483647: {exc}"
        ) from exc

    # 3. Version Name
    raw_version_name = root.get(ANDROID_NS + "versionName")
    version_name = str(raw_version_name)[:1024] if raw_version_name is not None else None

    # 4. Split Name
    split_attr = root.get("split")
    if split_attr is None:
        split_attr = root.get(ANDROID_NS + "split")

    if split_attr is not None:
        split_name = split_attr.strip() if isinstance(split_attr, str) else str(split_attr).strip()
        if not split_name:
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME", "Split manifest declared empty split attribute"
            )
        if split_name.lower() in RESERVED_SPLIT_NAMES:
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME",
                "Split APK cannot declare reserved split name 'base'",
            )
        if not SPLIT_NAME_REGEX.fullmatch(split_name):
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME",
                f"Split manifest declared invalid split name '{split_name}'",
            )
    else:
        split_name = None

    return package_name, version_code, version_name, split_name


def inspect_apk_bytes(
    data: bytes, file_name: str
) -> tuple[PackageFile, bytes]:
    """Inspect in-memory APK bytes, check ZIP constraints, extract manifest and compute hash."""
    size_bytes = len(data)
    if size_bytes > MAX_FILE_SIZE:
        raise PackageSetIntegrityError(
            "UPLOAD_TOO_LARGE",
            f"File '{file_name}' size {size_bytes} exceeds 150 MiB limit",
            http_status=413,
        )

    try:
        archive = ZipFile(io.BytesIO(data))
    except BadZipFile as exc:
        raise PackageSetIntegrityError(
            "CORRUPTED_FILE", f"File '{file_name}' is not a valid ZIP: {exc}"
        ) from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            raise PackageSetIntegrityError(
                "CORRUPTED_FILE", f"File '{file_name}' exceeds maximum ZIP entry limit"
            )
        seen = set()
        total_expanded = 0
        for entry in entries:
            name = entry.filename
            if (
                name in seen
                or "\\" in entry.orig_filename
                or name.startswith("/")
                or ":" in name
                or ".." in PurePosixPath(name).parts
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise PackageSetIntegrityError(
                    "CORRUPTED_FILE", f"File '{file_name}' contains unsafe ZIP entry '{name}'"
                )
            seen.add(name)
            total_expanded += entry.file_size
            if (
                entry.file_size > MAX_SINGLE_ZIP_ENTRY
                or total_expanded > MAX_EXPANDED_ZIP
                or entry.file_size > max(1, entry.compress_size) * 200
            ):
                raise PackageSetIntegrityError(
                    "CORRUPTED_FILE", f"File '{file_name}' ZIP expansion limit exceeded"
                )
            if entry.flag_bits & 1:
                raise PackageSetIntegrityError(
                    "CORRUPTED_FILE", f"File '{file_name}' contains encrypted ZIP entry"
                )

        if "AndroidManifest.xml" not in seen:
            raise PackageSetIntegrityError(
                "CORRUPTED_FILE", f"File '{file_name}' is missing AndroidManifest.xml"
            )

        try:
            manifest_bytes = archive.read("AndroidManifest.xml")
        except Exception as exc:
            raise PackageSetIntegrityError(
                "CORRUPTED_FILE", f"Could not read AndroidManifest.xml in '{file_name}': {exc}"
            ) from exc

    pkg_name, v_code, v_name, split_name = inspect_axml(manifest_bytes)
    sha256 = hashlib.sha256(data).hexdigest()
    part = PackagePart.SPLIT if split_name is not None else PackagePart.BASE

    pkg_file = PackageFile(
        file_name=file_name,
        part=part,
        split_name=split_name,
        sha256=sha256,
        size_bytes=size_bytes,
        package_name=pkg_name,
        version_code=v_code,
        version_name=v_name,
    )
    return pkg_file, data


def validate_package_set(
    files: list[PackageFile] | Path | str,
    declared_manifest: PackageSetManifestInput | None = None,
    max_cumulative_size: int = MAX_PACKAGE_SET_SIZE,
) -> PackageSet:
    """Validate a set of PackageFile instances or directory against all 10 integrity rules."""
    if isinstance(files, (Path, str)):
        dir_path = Path(files)
        if not dir_path.is_dir():
            raise PackageSetIntegrityError(
                "EMPTY_PACKAGE_SET", f"Directory '{dir_path}' does not exist"
            )
        apk_paths = sorted(
            p for p in dir_path.iterdir() if p.name.lower().endswith(".apk") and p.is_file()
        )
        if not apk_paths:
            raise PackageSetIntegrityError("EMPTY_PACKAGE_SET", "Package set contains no APK files")
        if len(apk_paths) > 101:
            raise PackageSetIntegrityError(
                "PACKAGE_SET_TOO_LARGE",
                f"Package set contains {len(apk_paths)} APK files; "
                "maximum allowed is 101 (1 base + 100 splits)",
                http_status=413,
            )
        parsed_files = []
        for apk_path in apk_paths:
            pkg_file, _ = inspect_apk_bytes(apk_path.read_bytes(), apk_path.name)
            parsed_files.append(pkg_file)
        files = parsed_files

    # Rule 1: Empty Set
    if not files:
        raise PackageSetIntegrityError("EMPTY_PACKAGE_SET", "Package set contains no APK files")

    # Early rejection if > 101 files
    if len(files) > 101:
        raise PackageSetIntegrityError(
            "PACKAGE_SET_TOO_LARGE",
            f"Package set contains {len(files)} files; "
            "maximum allowed is 101 (1 base + 100 splits)",
            http_status=413,
        )

    # Rule 2: Single file size
    for f in files:
        if f.size_bytes > MAX_FILE_SIZE:
            raise PackageSetIntegrityError(
                "UPLOAD_TOO_LARGE",
                f"File '{f.file_name}' size {f.size_bytes} exceeds 150 MiB limit",
                http_status=413,
            )

    # Rule 3: Cumulative Size
    total_size = sum(f.size_bytes for f in files)
    if total_size > max_cumulative_size:
        raise PackageSetIntegrityError(
            "PACKAGE_SET_TOO_LARGE",
            f"Package set cumulative size {total_size} exceeds 150 MiB limit",
            http_status=413,
        )

    # Rule 4: Exactly One Base APK (Missing or Multiple)
    base_files = [f for f in files if f.part == PackagePart.BASE]
    if not base_files:
        raise PackageSetIntegrityError(
            "MISSING_BASE_APK", "Package set contains no base APK (all files are splits)"
        )
    if len(base_files) > 1:
        names = [f.file_name for f in base_files]
        raise PackageSetIntegrityError(
            "MULTIPLE_BASE_APKS", f"Package set contains multiple base APKs: {names}"
        )
    base = base_files[0]

    # Rule 5, 6, 7: Split Package, VersionCode, and SplitName Uniqueness
    splits = [f for f in files if f.part == PackagePart.SPLIT]
    seen_splits = set()
    for split in splits:
        if split.package_name != base.package_name:
            raise PackageSetIntegrityError(
                "SPLIT_PACKAGE_MISMATCH",
                f"Split '{split.file_name}' package name '{split.package_name}' "
                f"does not match base '{base.package_name}'",
            )
        if split.version_code != base.version_code:
            raise PackageSetIntegrityError(
                "VERSION_CODE_MISMATCH",
                f"Split '{split.file_name}' versionCode {split.version_code} "
                f"does not match base {base.version_code}",
            )
        if not split.split_name or not split.split_name.strip():
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME", f"Split '{split.file_name}' has empty split name"
            )
        if split.split_name.strip().lower() in RESERVED_SPLIT_NAMES:
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME",
                "Split APK cannot declare reserved split name 'base'",
            )
        if not SPLIT_NAME_REGEX.fullmatch(split.split_name):
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME",
                f"Split '{split.file_name}' has invalid split name '{split.split_name}'",
            )
        if split.split_name in seen_splits:
            raise PackageSetIntegrityError(
                "DUPLICATE_SPLIT_NAME",
                f"Duplicate split name '{split.split_name}' in '{split.file_name}'",
            )
        seen_splits.add(split.split_name)

    # Rule 8: Declared Manifest SHA-256 Matching
    if declared_manifest is not None:
        if declared_manifest.package_name != base.package_name:
            raise PackageSetIntegrityError(
                "SPLIT_PACKAGE_MISMATCH",
                f"Declared manifest package '{declared_manifest.package_name}' does not match base",
            )
        if declared_manifest.version_code != base.version_code:
            raise PackageSetIntegrityError(
                "VERSION_CODE_MISMATCH",
                f"Declared manifest versionCode {declared_manifest.version_code} "
                f"does not match base",
            )
        declared_map = {f.file_name: f for f in declared_manifest.files}
        actual_map = {f.file_name: f for f in files}
        if set(declared_map.keys()) != set(actual_map.keys()):
            raise PackageSetIntegrityError(
                "SHA256_MISMATCH",
                "Declared manifest file inventory does not match uploaded files",
            )
        for name, decl in declared_map.items():
            act = actual_map[name]
            if decl.sha256 != act.sha256:
                raise PackageSetIntegrityError(
                    "SHA256_MISMATCH",
                    f"File '{name}' SHA-256 mismatch: declared '{decl.sha256}', "
                    f"computed '{act.sha256}'",
                )
            if decl.size_bytes != act.size_bytes:
                raise PackageSetIntegrityError(
                    "SHA256_MISMATCH",
                    f"File '{name}' size mismatch: declared {decl.size_bytes}, "
                    f"computed {act.size_bytes}",
                )

    return PackageSet(
        package_name=base.package_name,
        version_code=base.version_code,
        version_name=base.version_name,
        base=base,
        splits=splits,
        total_size_bytes=total_size,
    )


def parse_package_input(
    raw_data: bytes,
    declared_manifest: PackageSetManifestInput | None = None,
    default_name: str = "input.apk",
) -> tuple[PackageSet, dict[str, bytes]]:
    """Parse raw bytes which can be a single standalone APK or a .zip/.apks container.

    Returns:
        (PackageSet, {filename: file_bytes})
    """
    if len(raw_data) == 0:
        raise PackageSetIntegrityError("EMPTY_PACKAGE_SET", "Input data is empty")

    if len(raw_data) > MAX_PACKAGE_SET_SIZE:
        raise PackageSetIntegrityError(
            "PACKAGE_SET_TOO_LARGE",
            f"Input size {len(raw_data)} exceeds 150 MiB limit",
            http_status=413,
        )

    try:
        archive = ZipFile(io.BytesIO(raw_data))
    except BadZipFile as exc:
        raise PackageSetIntegrityError(
            "CORRUPTED_FILE", f"Uploaded input is not a valid ZIP/APK archive: {exc}"
        ) from exc

    with archive:
        names = archive.namelist()
        if "AndroidManifest.xml" in names:
            # Single APK file
            pkg_file, data = inspect_apk_bytes(raw_data, default_name)
            pkg_set = validate_package_set([pkg_file], declared_manifest=declared_manifest)
            return pkg_set, {default_name: raw_data}

        # Multi-package container archive (.apks or .zip)
        apk_entries = [
            n
            for n in names
            if re.search(r"\.apk$", n, re.IGNORECASE)
            and not n.startswith("__MACOSX")
            and not n.endswith("/")
        ]
        if not apk_entries:
            raise PackageSetIntegrityError(
                "EMPTY_PACKAGE_SET", "Archive contains no .apk files"
            )

        file_models = []
        apk_payloads = {}
        for entry_name in apk_entries:
            clean_name = PurePosixPath(entry_name).name
            entry_bytes = archive.read(entry_name)
            model, data = inspect_apk_bytes(entry_bytes, clean_name)
            file_models.append(model)
            apk_payloads[clean_name] = data

        pkg_set = validate_package_set(file_models, declared_manifest=declared_manifest)
        return pkg_set, apk_payloads
