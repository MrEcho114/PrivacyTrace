"""Bounded redaction for acceptance receipts and probe output.

Redaction is deliberately narrow. It masks recognisable credential shapes and
private home directories, while documented deployment paths, hostnames, ports,
image digests and envelope fields stay readable so a receipt remains usable as
evidence.

Two scan profiles exist:

* :func:`redact_text` is the conservative masker applied to every receipt.
* :func:`find_secret_markers` is the detector used by audits and by the receipt
  self-check. It returns category counts only, never the matched text.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

MASK = "***"
PRIVATE_KEY_MASK = "[REDACTED-PRIVATE-KEY]"
PRIVATE_HOME_MASK = "<private-home>"
PRIVATE_PATH_MASK = "<private-path>"

PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN[ A-Z0-9]*PRIVATE KEY-----.*?-----END[ A-Z0-9]*PRIVATE KEY-----",
    re.DOTALL,
)
CAPABILITY_TOKEN = re.compile(r"pt_cap_[A-Za-z0-9_-]{20,}")
#: ``Authorization: <Scheme> <credential>``. Padding ``=`` is allowed only at the
#: end, so response-header text such as ``Basic realm=synthetic`` never matches.
AUTHORIZATION_SCHEME = re.compile(
    r"(?i)\b(Bearer|Basic)[ \t]+(?P<credential>[A-Za-z0-9._~+/-]{15,}={0,2})(?![\w.=~+/-])"
)
#: Credential URLs carry a colon in userinfo, so a bare
#: ``scheme://host/`` or a control-protocol URI never matches. The user part may
#: be empty, as in Redis password-only DSNs.
URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]{1,15}://)"
    r"[^\s/@\"'?:]{0,120}:[^\s/@\"']{0,120}@"
)
INLINE_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?P<key>\b(?:requirepass|password|passwd|pwd|secret|token|api[_-]?key|"
    r"private[_-]?key|authorization|credential)\b)"
    r"(?P<quote>[\"']?)"
    r"(?P<sep>[ \t]*[:=][ \t]*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
POSIX_PRIVATE_HOME = re.compile(r"(?<![\w.-])/(?:home|Users)/[A-Za-z0-9._@-]+")
ROOT_HOME = re.compile(r"(?<![\w.-])/root(?=[/\\\s\"']|$)")
WINDOWS_PRIVATE_HOME = re.compile(r"(?i)(?<![\w])[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'<>|]+")
PRIVATE_PATH_MARKERS = (POSIX_PRIVATE_HOME, ROOT_HOME, WINDOWS_PRIVATE_HOME)

# Categories that are safe to flag in ordinary source text. Secret-assignment
# and private-path detection stay receipt-scoped: documented files legitimately
# contain "PT_SECRETS_DIR=" and synthetic path fixtures.
SOURCE_AUDIT_CATEGORIES = (
    "capability-token",
    "private-key-block",
    "url-credentials",
    "authorization-header",
)
RECEIPT_AUDIT_CATEGORIES = SOURCE_AUDIT_CATEGORIES + (
    "secret-assignment",
    "private-path",
)

_MARKERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "capability-token": (CAPABILITY_TOKEN,),
    "private-key-block": (PRIVATE_KEY_BLOCK,),
    "url-credentials": (URL_CREDENTIALS,),
    "authorization-header": (AUTHORIZATION_SCHEME,),
    "secret-assignment": (INLINE_SECRET_ASSIGNMENT,),
    "private-path": PRIVATE_PATH_MARKERS,
}


def _quoted_value(match: "re.Match[str]") -> str:
    value = match.group("value")
    if value[:1] in {'"', "'"}:
        return value[0] + MASK + value[0]
    return MASK


def _mask_secret_assignment(match: "re.Match[str]") -> str:
    return f"{match.group('key')}{match.group('quote')}{match.group('sep')}{_quoted_value(match)}"


def _mask_url_credentials(match: "re.Match[str]") -> str:
    return f"{match.group('scheme')}{MASK}@"


def _path_variants(value: str) -> Iterable[str]:
    seen = {value}
    forward = value.replace("\\", "/")
    native = value.replace("/", "\\")
    seen.update({forward, native, forward.rstrip("/"), native.rstrip("\\")})
    return (variant for variant in seen if len(variant) >= 6)


def redact_text(text: str, *, extra_paths: Sequence[str] = ()) -> str:
    """Mask credentials and host-private directories in ``text``."""
    if not text:
        return text
    for path in extra_paths:
        if not path:
            continue
        for variant in _path_variants(str(path)):
            text = re.sub(re.escape(variant), PRIVATE_PATH_MASK, text, flags=re.IGNORECASE)
    text = PRIVATE_KEY_BLOCK.sub(PRIVATE_KEY_MASK, text)
    text = AUTHORIZATION_SCHEME.sub(lambda m: f"{m.group(1)} {MASK}", text)
    text = CAPABILITY_TOKEN.sub(MASK, text)
    text = URL_CREDENTIALS.sub(_mask_url_credentials, text)
    text = INLINE_SECRET_ASSIGNMENT.sub(_mask_secret_assignment, text)
    text = POSIX_PRIVATE_HOME.sub(PRIVATE_HOME_MASK, text)
    text = ROOT_HOME.sub(PRIVATE_HOME_MASK, text)
    text = WINDOWS_PRIVATE_HOME.sub(PRIVATE_HOME_MASK, text)
    return text


def redact_value(value: Any, *, extra_paths: Sequence[str] = ()) -> Any:
    """Recursively redact strings inside JSON-compatible structures."""
    if isinstance(value, str):
        return redact_text(value, extra_paths=extra_paths)
    if isinstance(value, Mapping):
        return {
            redact_text(str(key)): redact_value(item, extra_paths=extra_paths)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_value(item, extra_paths=extra_paths) for item in value]
    return value


def find_secret_markers(
    text: str, *, categories: Sequence[str] = RECEIPT_AUDIT_CATEGORIES
) -> dict[str, int]:
    """Return ``{category: count}`` for markers found in ``text``.

    Only counts are returned; the matched text is never exposed, so an audit can
    report a finding without republishing the secret.
    """
    found: dict[str, int] = {}
    for category in categories:
        count = sum(len(pattern.findall(text)) for pattern in _MARKERS[category])
        if count:
            found[category] = count
    return found


def is_clean(text: str, *, categories: Sequence[str] = RECEIPT_AUDIT_CATEGORIES) -> bool:
    return not find_secret_markers(text, categories=categories)
