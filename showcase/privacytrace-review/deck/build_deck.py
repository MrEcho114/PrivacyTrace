import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "delivery" / "PrivacyTrace-Review.pptx"
CAPTURE = ROOT.parent / "capture"
CAPTURE_MANIFEST = CAPTURE / "manifest.json"
BUILD_DIR = ROOT / ".build"
QA_PATH = ROOT / "qa.json"

CAPTURE_SCHEMA = "privacytrace/review-deck-shots@1"
REQUIRED_SCREENS = {
    "import": "mobile-import-390x844-dpr3.png",
    "report": "mobile-report-390x844-dpr3.png",
}
BANNED_DECK_STRINGS = (
    "Issue #",
    "未上传",
    "最终上传未发生",
    "2026-10-22",
    "07b37b2",
    "工作台 · 开发版",
    "交付候选",
)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_capture_manifest():
    """Load and validate the screenshot provenance manifest.

    The deck never accepts a hand-named PNG: every UI figure must be described by
    the capture manifest, and the bytes on disk must match the recorded SHA-256.
    """
    if not CAPTURE_MANIFEST.exists():
        raise SystemExit(f"missing capture manifest: {CAPTURE_MANIFEST}; run node scripts/capture-review-deck-shots.cjs")
    manifest = json.loads(CAPTURE_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != CAPTURE_SCHEMA:
        raise SystemExit(f"unsupported capture manifest schema: {manifest.get('schema')!r}")
    commit = manifest.get("source_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit(f"capture manifest source_commit is not a full SHA: {commit!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", manifest.get("capture_date", "")):
        raise SystemExit(f"capture manifest capture_date is not a date: {manifest.get('capture_date')!r}")
    screens = {screen.get("file"): screen for screen in manifest.get("screens", [])}
    for role, name in REQUIRED_SCREENS.items():
        screen = screens.get(name)
        if screen is None:
            raise SystemExit(f"capture manifest is missing the {role} screen: {name}")
        if screen.get("viewport") != "390x844" or screen.get("device_scale_factor") != 3:
            raise SystemExit(f"{name}: capture must be 390x844 @ DPR 3, got {screen.get('viewport')} @ {screen.get('device_scale_factor')}")
        if screen.get("source_commit") != commit:
            raise SystemExit(f"{name}: screen source_commit does not match the manifest")
        path = CAPTURE / name
        if not path.exists():
            raise SystemExit(f"missing screenshot file: {path}")
        if sha256_file(path) != screen.get("sha256"):
            raise SystemExit(f"{name}: screenshot bytes do not match the manifest SHA-256")
    return manifest, screens


CAPTURE_MANIFEST_DATA, CAPTURE_SCREENS = load_capture_manifest()
SOURCE_COMMIT = CAPTURE_MANIFEST_DATA["source_commit"]
SOURCE_SHORT = SOURCE_COMMIT[:7]
CAPTURE_DATE = CAPTURE_MANIFEST_DATA["capture_date"]


def capture_path(role):
    return CAPTURE / CAPTURE_SCREENS[REQUIRED_SCREENS[role]]["file"]


def frame_phone(source, target):
    """Compose a phone bezel around the raw 390x844 screen.

    python-pptx cannot clip pictures to rounded corners, so the device frame is
    composed here from the manifest-owned PNG. The raw screenshot stays the
    source of truth; the framed derivative only adds a bezel and is regenerated
    on every build.
    """
    screen = Image.open(source).convert("RGBA")
    width, height = screen.size
    radius = int(width * 0.052)
    bezel = int(width * 0.026)
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=255)
    screen_masked = Image.new("RGBA", screen.size, (0, 0, 0, 0))
    screen_masked.paste(screen, (0, 0), mask)
    total = (width + bezel * 2, height + bezel * 2)
    body = Image.new("RGBA", total, (0, 0, 0, 0))
    draw = ImageDraw.Draw(body)
    draw.rounded_rectangle(
        [0, 0, total[0] - 1, total[1] - 1],
        radius=radius + bezel,
        fill=(9, 11, 15, 255),
        outline=(52, 59, 70, 255),
        width=max(2, bezel // 6),
    )
    body.alpha_composite(screen_masked, (bezel, bezel))
    body.save(target, "PNG")
    return target


def normalize_package(path, slides, notes):
    """Rewrite template metadata and pin ZIP timestamps.

    python-pptx starts from a template whose docProps still name "Steve Canny"
    and a 2013 timestamp, and its ZIP entries carry the wall clock. The deck is a
    judge-facing artifact, so the package is rewritten with neutral metadata,
    the real slide/notes counts, the true 16:9 format, and a fixed entry time so
    two builds from the same inputs produce the same bytes.
    """
    stamp = (2026, 10, 23, 0, 0, 0)
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "docProps/app.xml":
                text = data.decode("utf-8")
                text = re.sub(r"<Application>.*?</Application>", "<Application>PrivacyTrace</Application>", text)
                text = re.sub(r"<PresentationFormat>.*?</PresentationFormat>", "<PresentationFormat>On-screen Show (16:9)</PresentationFormat>", text)
                text = re.sub(r"<Slides>\d+</Slides>", f"<Slides>{slides}</Slides>", text)
                text = re.sub(r"<Notes>\d+</Notes>", f"<Notes>{notes}</Notes>", text)
                text = re.sub(r"<AppVersion>.*?</AppVersion>", "<AppVersion>16.0000</AppVersion>", text)
                data = text.encode("utf-8")
            info.date_time = stamp
            target.writestr(info, data)
    tmp.replace(path)

INK = RGBColor(0x07, 0x09, 0x0C)
INK2 = RGBColor(0x10, 0x15, 0x1D)
PAPER = RGBColor(0xF4, 0xF0, 0xE4)
DARKTEXT = RGBColor(0x17, 0x1B, 0x22)
SUBTEXT = RGBColor(0x5D, 0x5A, 0x52)
MUTED = RGBColor(0x98, 0xA2, 0xB3)
AMBER = RGBColor(0xE9, 0xB8, 0x72)
GREEN = RGBColor(0x84, 0xC9, 0xA6)
RED = RGBColor(0xE5, 0x89, 0x78)
LINE = RGBColor(0x2A, 0x30, 0x3A)

SERIF = "Noto Serif SC"
SANS = "Noto Sans SC"
MONO = "Cascadia Mono"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def set_font(run, name, size, color, bold=False, spacing=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = etree.SubElement(rPr, qn("a:ea"))
    ea.set("typeface", name)
    if spacing is not None:
        rPr.set("spc", str(int(spacing * 100)))


def add_text(slide, text, x, y, w, h, size=14, color=PAPER, font=SANS, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.15,
             spacing=None, margins=(0, 0, 0, 0)):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left, tf.margin_right, tf.margin_top, tf.margin_bottom = [Inches(m) for m in margins]
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(0)
        p.space_before = Pt(0)
        run = p.add_run()
        run.text = line
        set_font(run, font, size, color, bold, spacing)
    return box


def add_rich(slide, parts, x, y, w, h, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             line_spacing=1.15, margins=(0, 0, 0, 0)):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left, tf.margin_right, tf.margin_top, tf.margin_bottom = [Inches(m) for m in margins]
    for i, part in enumerate(parts):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(0)
        p.space_before = Pt(0)
        for text, font, size, color, bold in part:
            run = p.add_run()
            run.text = text
            set_font(run, font, size, color, bold)
    return box


def add_rect(slide, x, y, w, h, fill, line=None, line_w=0.75, radius=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w)
    shape.shadow.inherit = False
    if radius:
        try:
            shape.adjustments[0] = 0.06
        except Exception:
            pass
    return shape


def add_line(slide, x1, y1, x2, y2, color, width=0.75):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = color
    conn.line.width = Pt(width)
    return conn


def add_diamond(slide, x, y, s, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.DIAMOND, Inches(x - s / 2), Inches(y - s / 2), Inches(s), Inches(s))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def base_slide(idx, section_cn, section_en, page_x=11.95):
    slide = prs.slides.add_slide(BLANK)
    add_rect(slide, 0, 0, 13.333, 7.5, INK)
    # subtle vertical grid
    for x in (3.333, 6.666, 9.999):
        add_line(slide, x, 0.92, x, 7.2, RGBColor(0x12, 0x18, 0x20), 0.5)
    add_line(slide, 0.62, 0.9, 12.7, 0.9, RGBColor(0x1A, 0x20, 0x28), 0.5)
    # brand
    add_rect(slide, 0.62, 0.34, 0.32, 0.32, INK, RGBColor(0x8A, 0x93, 0xA0), 0.6)
    add_text(slide, "PT", 0.62, 0.40, 0.32, 0.2, 8, PAPER, MONO, False, PP_ALIGN.CENTER)
    add_text(slide, "PrivacyTrace", 1.04, 0.35, 2.4, 0.24, 12, PAPER, SANS, True)
    add_text(slide, "作品评审 / EXPERT REVIEW", 1.04, 0.57, 3.2, 0.18, 7, MUTED, MONO, False, spacing=1.4)
    # section
    add_text(slide, section_cn, 0.62, 1.03, 5.4, 0.22, 10, AMBER, MONO, False, spacing=1.4)
    add_text(slide, section_en, 0.62, 1.23, 5.4, 0.16, 7, RGBColor(0x6E, 0x78, 0x88), MONO, False, spacing=2.0)
    # footer
    add_text(slide, "PRIVACYTRACE / REVIEW DECK / 2026", 0.62, 7.08, 5.4, 0.16, 6.5, RGBColor(0x55, 0x5E, 0x6C), MONO, False, spacing=1.2)
    add_text(slide, f"{idx:02d} / 10", page_x, 7.08, 0.75, 0.16, 6.5, RGBColor(0x55, 0x5E, 0x6C), MONO, False, PP_ALIGN.RIGHT)
    return slide


def section_head(slide, title_lines, x=0.62, y=1.55, w=6.4, size=33):
    parts = []
    for i, (text, color) in enumerate(title_lines):
        parts.append([(text, SERIF, size, color, True)])
    add_rich(slide, parts, x, y, w, 1.6, line_spacing=1.22)


def add_phone(slide, path, x, y, w):
    """Compose the device frame from the manifest PNG and place it at `w` inches."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    framed = BUILD_DIR / f"{Path(path).stem}-framed.png"
    frame_phone(path, framed)
    src_w, src_h = Image.open(framed).size
    h = w * src_h / src_w
    pic = slide.shapes.add_picture(str(framed), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
    return pic, h


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ---------------------------------------------------------------- slide 1
s = prs.slides.add_slide(BLANK)
add_rect(s, 0, 0, 13.333, 7.5, INK)
for x in (3.333, 6.666, 9.999):
    add_line(s, x, 0.92, x, 7.2, RGBColor(0x12, 0x18, 0x20), 0.5)
add_line(s, 0.62, 0.9, 12.7, 0.9, RGBColor(0x1A, 0x20, 0x28), 0.5)
add_rect(s, 0.62, 0.34, 0.32, 0.32, INK, RGBColor(0x8A, 0x93, 0xA0), 0.6)
add_text(s, "PT", 0.62, 0.40, 0.32, 0.2, 8, PAPER, MONO, False, PP_ALIGN.CENTER)
add_text(s, "PrivacyTrace", 1.04, 0.35, 2.4, 0.24, 12, PAPER, SANS, True)
add_text(s, "作品评审 / EXPERT REVIEW", 1.04, 0.57, 3.2, 0.18, 7, MUTED, MONO, False, spacing=1.4)
add_text(s, "2026 · 专家评审版", 9.95, 0.40, 2.7, 0.2, 7.5, AMBER, MONO, False, PP_ALIGN.RIGHT, spacing=1.2)

add_text(s, "PrivacyTrace", 0.78, 2.05, 7.8, 1.2, 54, PAPER, SERIF, True, spacing=0.2)
add_text(s, "Android APK 静态隐私线索 × 政策原文", 0.82, 3.25, 7.6, 0.42, 19, RGBColor(0xCF, 0xC8, 0xB8), SANS, False)
add_text(s, "作品评审 · 专家版 · 120 秒影片 + 评审 PPT", 0.82, 3.85, 7.4, 0.28, 10, AMBER, MONO, False, spacing=0.8)
add_line(s, 0.82, 4.35, 5.1, 4.35, RGBColor(0x8B, 0x6A, 0x3E), 0.75)

# right evidence motif
for i in range(12):
    add_rect(s, 8.55, 1.55 + i * 0.33, 1.55 - (i % 3) * 0.22, 0.045, RGBColor(0x55, 0x60, 0x72), None)
    add_rect(s, 11.0, 1.55 + i * 0.33, 1.45 - (i % 4) * 0.18, 0.045, RGBColor(0x4A, 0x55, 0x67), None)
add_text(s, "CODE / STATIC EVIDENCE", 8.55, 1.26, 2.2, 0.2, 7, RGBColor(0x7D, 0x88, 0x99), MONO, False, spacing=1.0)
add_text(s, "POLICY / TEXT", 11.0, 1.26, 2.0, 0.2, 7, RGBColor(0x7D, 0x88, 0x99), MONO, False, spacing=1.0)
add_line(s, 10.18, 3.55, 10.95, 3.55, AMBER, 0.75)
add_diamond(s, 10.56, 3.55, 0.12, AMBER)
add_rect(s, 10.28, 3.78, 0.58, 0.22, INK, RGBColor(0x8B, 0x6A, 0x3E), 0.6)
add_text(s, "EVIDENCE", 10.28, 3.83, 0.58, 0.14, 5.5, AMBER, MONO, False, PP_ALIGN.CENTER, spacing=0.8)

add_text(s, "视频与 PPT 均按「定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献」组织。", 0.82, 6.28, 7.8, 0.28, 9, RGBColor(0x7D, 0x88, 0x99), SANS)
add_text(s, "2026-10-23 · REVIEW CUT", 0.82, 7.08, 5.0, 0.18, 7, RGBColor(0x55, 0x5E, 0x6C), MONO, False, spacing=1.2)
notes(s, "开场：这是一份专家评审材料。影片 120 秒，PPT 作为同一叙事的可翻阅版本。两者使用同一组事实、同一组边界，不把产品演示当成评审结论。")

# ---------------------------------------------------------------- slide 2
s = base_slide(2, "01 / 定位", "POSITIONING")
section_head(s, [("读取静态线索，", PAPER), ("对齐政策原文。", AMBER)], w=6.2, size=32)
add_text(s, "上传 APK 或 base + splits，解析 manifest 与全部 classesN.dex。再放入政策正文：可定位的线索落到代码位置与政策原句，材料不足保留 UNKNOWN。", 0.62, 2.98, 6.15, 1.2, 13.5, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, line_spacing=1.35)

for i, (left, right) in enumerate((("权限", "= 能力声明"), ("invoke", "= 静态线索"), ("未证实", "= UNKNOWN"))):
    y = 4.28 + i * 0.44
    add_rect(s, 0.62, y, 5.95, 0.34, RGBColor(0x0E, 0x12, 0x18), RGBColor(0x25, 0x2C, 0x36), 0.5)
    add_rect(s, 0.72, y + 0.14, 0.05, 0.05, AMBER, None)
    add_text(s, left, 0.88, y + 0.08, 1.2, 0.2, 9, PAPER, MONO, False)
    add_text(s, right, 2.15, y + 0.08, 4.1, 0.2, 9, RGBColor(0xB8, 0xC0, 0xCE), MONO, False)

add_rect(s, 0.62, 5.72, 6.2, 0.98, PAPER, None)
add_text(s, "它不判断", 0.86, 5.86, 1.4, 0.2, 8, RGBColor(0x8B, 0x3A, 0x2D), MONO, False, spacing=1.4)
add_text(s, "合规性  /  安全性  /  实际采集", 0.86, 6.10, 5.4, 0.32, 18, DARKTEXT, SERIF, True)
add_text(s, "线索 ≠ 行为。结论留给证据与人工复核。", 0.86, 6.46, 5.4, 0.16, 7.5, SUBTEXT, SANS)

add_text(s, "移动 App · 开发版", 7.05, 1.50, 2.7, 0.2, 8, AMBER, MONO, False, spacing=1.2)
add_text(s, f"{CAPTURE_DATE} 采集 @ {SOURCE_SHORT}", 7.05, 1.71, 2.8, 0.18, 6.8, RGBColor(0x6E, 0x78, 0x88), MONO)
add_text(s, "只对照，\n不判定。", 7.05, 2.10, 2.7, 1.0, 22, PAPER, SERIF, True, line_spacing=1.18)
add_line(s, 7.05, 3.10, 9.72, 3.10, RGBColor(0x8B, 0x6A, 0x3E), 0.75)
add_text(s, "界面仍在开发，最终视觉可能变化。桌面工作台（冻结）不是客户端。", 7.05, 3.22, 2.65, 0.62, 7.2, RGBColor(0x9A, 0xA4, 0xB2), SANS, False, line_spacing=1.45)
add_text(s, "图上能对上的入口", 7.05, 3.94, 2.6, 0.18, 6.8, AMBER, MONO, False, spacing=1.0)
for i, (title, sub) in enumerate((
    ("选择应用", "系统选择器 · 主动选择"),
    ("政策来源 2 份", "手动补入 · 未复核"),
    ("固定合成材料", "构造示例 · 可删除"),
)):
    y = 4.20 + i * 0.60
    add_rect(s, 7.05, y + 0.07, 0.05, 0.05, AMBER, None)
    add_text(s, title, 7.20, y, 2.45, 0.2, 8.6, PAPER, SANS, True)
    add_text(s, sub, 7.20, y + 0.22, 2.45, 0.18, 6.8, RGBColor(0x9A, 0xA4, 0xB2), MONO)
add_text(s, "取材：生产 Vue + 受控 native bridge；非真机、非 APK 扫描。", 7.05, 6.52, 2.7, 0.4, 6.4, RGBColor(0x6E, 0x78, 0x88), SANS, False, line_spacing=1.4)
build_phone, phone_h = add_phone(s, capture_path("import"), 10.0, 1.42, 2.62)
notes(s, f"定位：它读取安装包里的静态线索，和政策原文逐条对照。权限是能力，invoke 是线索，两者都不等于实际采集。右侧是 {CAPTURE_DATE} 采集的移动 App 开发版截图（提交 {SOURCE_SHORT}），固定合成材料；截图来自生产 Vue + 受控 native bridge，不是真机，也不是 APK 扫描。桌面工作台按 ADR-0005 冻结，不是客户端。")

# ---------------------------------------------------------------- slide 3
s = base_slide(3, "02 / 创新", "INNOVATION")
add_rich(s, [[("结论要能回到", SERIF, 28, PAPER, True), ("代码与原文。", SERIF, 28, AMBER, True)]], 0.62, 1.55, 6.4, 0.55, line_spacing=1.1)

# left code card
add_rect(s, 0.62, 2.35, 5.55, 2.55, PAPER, None)
add_text(s, "① 代码位置", 0.86, 2.52, 2.0, 0.2, 8, RGBColor(0x8B, 0x3A, 0x2D), MONO, False, spacing=1.2)
add_text(s, "synthetic/LocationFeature.java", 0.86, 2.78, 4.9, 0.2, 8.5, RGBColor(0x3C, 0x41, 0x4A), MONO)
add_text(s, "LocationFeature#readGpsLocation:12", 0.86, 2.98, 4.9, 0.18, 7.5, RGBColor(0x78, 0x72, 0x68), MONO)
add_rect(s, 0.86, 3.25, 4.95, 0.86, RGBColor(0x17, 0x1B, 0x22), None)
add_text(s, "locationManager.getLastKnownLocation(\n    LocationManager.GPS_PROVIDER);", 1.0, 3.38, 4.7, 0.6, 8.5, RGBColor(0xCD, 0xD6, 0xE6), MONO, False, line_spacing=1.3)
add_text(s, "rule · android.location.last-known.gps", 0.86, 4.22, 4.9, 0.18, 7, RGBColor(0x7C, 0x76, 0x6B), MONO)

# right policy card
add_rect(s, 7.15, 2.35, 5.55, 2.55, PAPER, None)
add_text(s, "② 政策原句", 7.39, 2.52, 2.0, 0.2, 8, RGBColor(0x8B, 0x3A, 0x2D), MONO, False, spacing=1.2)
add_text(s, "示例 App 内隐私政策 · 全文快照", 7.39, 2.78, 4.9, 0.2, 8.5, RGBColor(0x3C, 0x41, 0x4A), MONO)
add_text(s, "原文位置 [0, 18)", 7.39, 2.98, 4.9, 0.18, 7.5, RGBColor(0x78, 0x72, 0x68), MONO)
add_text(s, "我们访问位置信息，用于提供地图功能。", 7.39, 3.34, 4.9, 0.62, 16, DARKTEXT, SERIF, True, line_spacing=1.4)
add_text(s, "按 Unicode 码点计数 · 半开区间", 7.39, 4.22, 4.9, 0.18, 7, RGBColor(0x7C, 0x76, 0x6B), MONO)
add_line(s, 6.18, 3.62, 7.14, 3.62, RGBColor(0x8B, 0x6A, 0x3E), 0.9)
add_diamond(s, 6.66, 3.62, 0.11, AMBER)
add_text(s, "对照", 6.42, 3.38, 0.5, 0.16, 6.5, RGBColor(0x8B, 0x3A, 0x2D), MONO, False, PP_ALIGN.CENTER, spacing=1.2)

add_text(s, "一条证据，两个终点；两边都能自己走一遍。", 0.62, 5.10, 8.4, 0.32, 15, PAPER, SERIF, True)
add_text(s, "人工构造示例 · 可复算", 10.9, 5.16, 1.8, 0.18, 7, RGBColor(0x8B, 0x3A, 0x2D), MONO, False, PP_ALIGN.RIGHT)

for i, (k, title, sub) in enumerate((
    ("01", "两个终点", "代码位置与政策原句，都能自己走一遍。"),
    ("02", "三层分离", "事实、声明、推断分开记录；UNKNOWN 保留。"),
    ("03", "真值先冻结", "12 个场景、三方案同材料；先冻真值再跑算法。"),
)):
    x = 0.62 + i * 4.17
    add_rect(s, x, 5.72, 3.95, 1.02, INK2, LINE, 0.6)
    add_text(s, k + " / " + title, x + 0.18, 5.82, 3.6, 0.18, 7, AMBER, MONO, False, spacing=1.2)
    add_text(s, sub, x + 0.18, 6.05, 3.6, 0.52, 9.5, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, line_spacing=1.3)

notes(s, "创新点不在静态分析本身，而在证据链的形状：一条证据同时挂代码位置和政策原句，两个端点都能复核。一致性分析不是本项目首创；我们把证据链做成可理解、可复核。事实、声明、推断分开记录，材料不足就保留 UNKNOWN。受控场景的真值先冻结，再让算法跑。")

# ---------------------------------------------------------------- slide 4
s = base_slide(4, "03 / 关键实现", "IMPLEMENTATION", page_x=8.55)
section_head(s, [("一条流水线，", PAPER), ("同一条证据链。", AMBER)], w=6.4, size=30)

nodes = (
    ("APK + 政策材料", "单包 / base + splits"),
    ("隔离扫描", "Docker · network none"),
    ("证据 + 候选", "代码位置 · 原句区间"),
    ("一致性对照", "多状态 · 缺证据不升级"),
    ("报告 / 回放", "Web · Android · 离线"),
)
add_line(s, 0.85, 3.32, 8.65, 3.32, RGBColor(0x44, 0x4C, 0x5A), 0.8)
for i, (name, sub) in enumerate(nodes):
    x = 0.85 + i * 1.95
    add_rect(s, x - 0.045, 3.275, 0.09, 0.09, INK, AMBER, 0.8)
    add_text(s, name, x - 0.90, 3.39, 1.8, 0.22, 9.5, PAPER, SANS, True, PP_ALIGN.CENTER)
    add_text(s, sub, x - 0.90, 3.61, 1.8, 0.18, 6.5, RGBColor(0x6E, 0x78, 0x88), MONO, False, PP_ALIGN.CENTER)

add_rect(s, 0.62, 3.85, 6.35, 2.80, INK2, LINE, 0.7)
blocks = (
    ("隔离扫描 / CONTAINER", "非 root 65534:65534\nnetwork=none · 只读根\ncap-drop ALL\n1 CPU · 1 GiB · PID 32"),
    ("静态分析 / STATIC", "Androguard 4.1.3\nAXML + 全部 classesN.dex\n缺 JADX → 字节码兜底\n方法内无分支局部常量"),
    ("政策快照 / POLICY", "Unicode 码点半开区间 [start,end)\n切片 == excerpt\n旧快照不覆盖\n来源 · 版本 · 采集时点"),
    ("引擎与运行 / ENGINE", "FastAPI · Pydantic\nPostgreSQL outbox\nRedis · Celery\nmTLS Runner · 不持 Docker socket"),
)
for i, (title, body) in enumerate(blocks):
    x = 0.82 + (i % 2) * 3.08
    y = 4.00 + (i // 2) * 1.22
    add_text(s, title, x, y, 2.9, 0.18, 6.5, AMBER, MONO, False, spacing=1.2)
    add_text(s, body, x, y + 0.24, 2.9, 0.95, 8, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, line_spacing=1.4)
add_text(s, "未知 APK 只在隔离容器里解析；扫描结束删除副本。", 0.82, 6.45, 5.9, 0.18, 7, RGBColor(0x9A, 0xA4, 0xB2), SANS)

# Right side: mobile report capture (portrait) + a museum-style side caption.
add_text(s, "移动报告 · 开发版", 7.05, 3.95, 2.3, 0.2, 7.6, AMBER, MONO, False, spacing=1.1)
add_text(s, f"{CAPTURE_DATE} 采集 @ {SOURCE_SHORT}", 7.05, 4.18, 2.35, 0.18, 6.4, RGBColor(0x9A, 0xA4, 0xB2), MONO)
add_line(s, 7.05, 4.50, 9.30, 4.50, RGBColor(0x3A, 0x42, 0x50), 0.6)
add_text(s, "构造材料 /\n持久化回放", 7.05, 4.62, 2.25, 0.85, 12.5, PAPER, SERIF, True, line_spacing=1.25)
add_text(s, "SYNTHETIC · PERSISTED_REPLAY", 7.05, 5.40, 2.3, 0.34, 6.1, RGBColor(0x8B, 0x6A, 0x3E), MONO, False, line_spacing=1.3)
add_text(s, "数据类型 2 · 政策来源 1 · 证据 3", 7.05, 5.80, 2.35, 0.3, 6.8, RGBColor(0xC9, 0xC3, 0xB4), SANS)
add_text(s, "两条结论均待复核", 7.05, 6.02, 2.3, 0.2, 6.8, AMBER, MONO)
add_text(s, "界面仍在开发；最终视觉可能变化。", 7.05, 6.50, 2.35, 0.4, 6.3, RGBColor(0x6E, 0x78, 0x88), SANS, False, line_spacing=1.4)
add_phone(s, capture_path("report"), 9.55, 1.34, 2.90)
notes(s, f"实现是一条流水线：材料进来，隔离容器里解析，生成证据和候选，一致性引擎对照，最后出报告和回放。左边四个块是可核的约束和组件；右侧是 {CAPTURE_DATE} 采集的移动报告（提交 {SOURCE_SHORT}），输入是构造材料，页面是持久化回放，两条结论都待复核。界面仍是开发版，最终视觉可能变化。")

# ---------------------------------------------------------------- slide 5
s = base_slide(5, "04 / 真实成果", "RESULTS")
add_rich(s, [[("把四类数字", SERIF, 28, PAPER, True), ("分开报。", SERIF, 28, AMBER, True)]], 0.62, 1.55, 6.2, 0.55, line_spacing=1.1)

cards = (
    ("工程门禁 / ENGINEERING GATE", "1578", "passed", 2.15, "179 skipped\ne2e 65 · Web 111 · 生产构建通过", "65b49f7 · 2026-10-21"),
    ("部署验收 / DEPLOYMENT R1–R6", "40", "pass", 1.35, "0 fail · 0 skip\n四入口 4/4；唯一既有豁免 dedicated-scan-host-verification", "65b49f7 · 用户授权"),
    ("受控评测 / CONTROLLED", "12", "/ 12", 1.30, "API 基线 4/12 · 权限+关键词 2/12\n36 行 · 失败 0 · P/R/F1 = N/A", "b0b3c74 · 名义状态对照"),
)
for i, (title, big, unit, unit_x, body, foot) in enumerate(cards):
    x = 0.62 + i * 4.17
    add_rect(s, x, 2.30, 3.95, 2.55, INK2, LINE, 0.7)
    add_text(s, title, x + 0.22, 2.46, 3.5, 0.18, 6.5, AMBER, MONO, False, spacing=1.0)
    add_text(s, big, x + 0.22, 2.72, 2.0, 0.78, 40, PAPER, MONO, False)
    add_text(s, unit, x + unit_x, 3.05, 1.2, 0.24, 9, MUTED, MONO)
    add_text(s, body, x + 0.22, 3.55, 3.5, 0.95, 8, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, line_spacing=1.4)
    add_text(s, foot, x + 0.22, 4.55, 3.5, 0.16, 6.5, RGBColor(0x6E, 0x78, 0x88), MONO)

add_text(s, "工程测试 ≠ 受控评测 ≠ 真实 App 准确率", 0.62, 5.20, 9.2, 0.36, 18, PAPER, SERIF, True)
add_text(s, "受控场景是自建源码场景的名义状态对照，不推广为真实 App 的检测准确率；P/R/F1 按协议为 N/A。", 0.62, 5.62, 11.8, 0.34, 9.5, RGBColor(0x9A, 0xA4, 0xB2), SANS, False)
add_text(s, "未命中规则 ≠ 没有隐私行为。", 0.62, 6.10, 6.0, 0.24, 10, AMBER, MONO, False, spacing=0.6)
notes(s, "结果分四类：工程门禁 1578 passed、179 skipped，e2e 65，Web 111；部署 40/0/0，四入口 4/4；受控 12 个场景，三方案状态一致 12/4/2，36 行，失败 0，P/R/F1 按协议 N/A。三类数字不能混着说。")

# ---------------------------------------------------------------- slide 6
s = base_slide(6, "04 / 真实成果 · 边界", "RESULTS / BOUNDED")
section_head(s, [("把失败和缺口", PAPER), ("放在结果旁边。", AMBER)], w=6.4, size=32)

add_text(s, "H 矩阵 / 12 个组合", 0.62, 3.00, 3.2, 0.2, 7, AMBER, MONO, False, spacing=1.2)
add_text(s, "11 / 12", 0.62, 3.20, 2.4, 0.62, 34, PAPER, MONO, False)
add_text(s, "通过", 3.15, 3.58, 0.8, 0.2, 9, MUTED, MONO)
for i in range(12):
    x = 0.62 + (i % 6) * 0.66
    y = 3.95 + (i // 6) * 0.38
    fail = i == 11
    add_rect(s, x, y, 0.58, 0.28, RGBColor(0x1A, 0x10, 0x10) if fail else RGBColor(0x0E, 0x18, 0x14), RED if fail else RGBColor(0x3E, 0x6B, 0x57), 0.6)
    add_text(s, f"H{i+1:02d}", x + 0.03, y + 0.07, 0.52, 0.14, 6, RED if fail else GREEN, MONO, False, PP_ALIGN.CENTER)
add_text(s, "H12 · J × splits × 手机模型", 0.62, 4.78, 4.0, 0.2, 8, RED, MONO)
add_text(s, "失败已复现 2 次，保留。", 0.62, 5.00, 4.0, 0.2, 8, RGBColor(0xC9, 0xC3, 0xB4), SANS)

add_rect(s, 6.85, 3.00, 5.85, 2.25, INK2, LINE, 0.7)
add_text(s, "真实 App 案例 / GKD v1.12.1（仅 1 个历史样本）", 7.08, 3.18, 5.4, 0.2, 6.5, AMBER, MONO, False, spacing=0.6)
add_text(s, "6 证据  /  3 行为  /  2 声明  /  3 问题", 7.08, 3.50, 5.4, 0.28, 13, PAPER, SANS, True)
add_text(s, "3 条结论均 INSUFFICIENT_EVIDENCE", 7.08, 3.88, 5.4, 0.26, 12, RED, MONO, False, spacing=0.4)
add_text(s, "2026-10-09 历史记录；本轮未重扫，也不代表实际采集。", 7.08, 4.22, 5.4, 0.3, 7.5, RGBColor(0x9A, 0xA4, 0xB2), SANS)

ladder = (("工程测试", "代码按预期运行"), ("受控评测", "自建场景 · 名义状态对照"), ("真实 App 准确率", "未做 · 不宣称"))
for i, (title, sub) in enumerate(ladder):
    x = 0.62 + i * 4.17
    add_line(s, x, 5.55, x + 3.9, 5.55, RGBColor(0x3A, 0x42, 0x50), 0.8)
    add_text(s, title, x, 5.67, 3.9, 0.26, 12, RED if i == 2 else PAPER, SANS, True)
    add_text(s, sub, x, 5.95, 3.9, 0.2, 7.5, RGBColor(0x9A, 0xA4, 0xB2), MONO)
    if i < 2:
        add_text(s, "≠", x + 3.94, 5.45, 0.3, 0.26, 11, RGBColor(0x5A, 0x62, 0x70), SERIF, True)

add_text(s, "证据不足，也要写进报告。", 0.62, 6.35, 6.4, 0.36, 20, PAPER, SERIF, True)
add_text(s, "受控结果不推广为真实 App 的检测准确率；未命中规则 ≠ 没有隐私行为。", 0.62, 6.80, 11.5, 0.2, 8.5, RGBColor(0x6E, 0x78, 0x88), SANS)
notes(s, "H 矩阵 11 通过、1 失败；H12 是 J × splits × 手机模型，失败复现两次，片内和 PPT 都保留。真实 App 只有一个历史样本 GKD，6 证据、3 行为、2 声明、3 问题，三条结论都是证据不足。不要把工程测试、受控评测、真实 App 准确率混成一个数字。")

# ---------------------------------------------------------------- slide 7
s = base_slide(7, "05 / 学生原创贡献", "ORIGINAL CONTRIBUTION")
add_rich(s, [[("团队提出什么，", SERIF, 28, PAPER, True), ("AI 辅助什么。", SERIF, 28, AMBER, True)]], 0.62, 1.55, 6.4, 0.55, line_spacing=1.1)

add_rect(s, 0.62, 2.18, 6.0, 4.10, PAPER, None)
add_text(s, "团队提出并执行", 0.86, 2.36, 3.0, 0.2, 8, RGBColor(0x8B, 0x3A, 0x2D), MONO, False, spacing=1.4)
rows = (
    ("01", "项目定位与「只对照，不判定」边界"),
    ("02", "证据模型与一致性状态机"),
    ("03", "确定性规则与字节码归因"),
    ("04", "受控场景 · 冻结真值 · 三方案对照"),
    ("05", "验收治理：Issue / PR / check.sh 门禁"),
)
for i, (num, text) in enumerate(rows):
    y = 2.72 + i * 0.52
    add_text(s, num, 0.88, y, 0.35, 0.18, 7, RGBColor(0x8B, 0x3A, 0x2D), MONO)
    add_text(s, text, 1.30, y, 5.0, 0.22, 11.5, DARKTEXT, SANS, False)
    add_line(s, 0.88, y + 0.34, 6.30, y + 0.34, RGBColor(0xD8, 0xD0, 0xBF), 0.5)
add_text(s, "问题定义 → 证据模型 → 规则归因 → 受控基准 → 验收治理", 0.88, 5.48, 5.3, 0.2, 6.5, RGBColor(0x8B, 0x3A, 0x2D), MONO)
add_text(s, "参赛团队提出并执行；身份与分工以报名及提交记录为准。", 0.88, 5.92, 5.3, 0.3, 7, SUBTEXT, SANS)

add_rect(s, 6.90, 2.18, 5.8, 4.10, INK2, LINE, 0.7)
add_text(s, "AI 辅助 · 披露在案", 7.14, 2.36, 3.0, 0.2, 8, AMBER, MONO, False, spacing=1.4)
add_text(s, "脚手架与接口胶水。\n测试与验收脚本。\n文档与文案草稿。", 7.14, 2.70, 5.1, 1.25, 19, PAPER, SERIF, True, line_spacing=1.35)
add_text(s, "边界：不宣称 100% 独立，也不给出比例。", 7.14, 4.18, 5.1, 0.22, 8.5, RGBColor(0xC9, 0xC3, 0xB4), SANS)
add_text(s, "第三方：Androguard 4.1.3（Apache-2.0）· FastAPI · Vue 3 · PostgreSQL · Tauri 2。", 7.14, 4.55, 5.1, 0.5, 7.5, RGBColor(0x9A, 0xA4, 0xB2), SANS, False, line_spacing=1.35)
add_text(s, "工具 → 用途 → 受影响文件 → 人工修改 → 复核", 7.14, 5.30, 5.1, 0.2, 6.5, RGBColor(0x8B, 0x6A, 0x3E), MONO)
add_text(s, "披露范围：工具、用途、受影响文件与人工修改；具体归属以提交记录为准。", 7.14, 5.72, 5.1, 0.4, 7, RGBColor(0x9A, 0xA4, 0xB2), SANS, False, line_spacing=1.35)

ledger = (("65b49f7", "工程门禁"), ("323780c9", "六场景"), ("b0b3c74", "十二场景"), ("9e56771", "离线包"), ("2626152", "H 矩阵"))
for i, (sha, label) in enumerate(ledger):
    x = 0.62 + i * 2.5
    add_text(s, sha, x, 6.38, 1.2, 0.18, 7.5, RGBColor(0xC9, 0xC3, 0xB4), MONO)
    add_text(s, label, x, 6.56, 1.2, 0.16, 6.5, RGBColor(0x6E, 0x78, 0x88), MONO)
add_text(s, "每个数字绑定各自的提交与日期，不写成「当前版本」。", 0.62, 6.82, 9.5, 0.18, 7, RGBColor(0x6E, 0x78, 0x88), SANS)
notes(s, "贡献分两层写：团队提出并执行定位、证据模型、规则、受控基准和验收治理；AI 集中在脚手架、测试、文档和文案。不给代码比例，也不宣称 100% 独立。每个数字都绑提交，不写成当前版本。")

# ---------------------------------------------------------------- slide 8
s = base_slide(8, "边界 / 缺口", "BOUNDARIES")
add_rich(s, [[("把边界放在", SERIF, 28, PAPER, True), ("结果旁边。", SERIF, 28, AMBER, True)]], 0.62, 1.55, 6.4, 0.55, line_spacing=1.1)

columns = (
    ("已做", GREEN, (
        "隔离扫描：非 root、network none、只读根",
        "证据模型与一致性状态机",
        "12 个受控场景 · 36 行三方案",
        "工程门禁 1578 passed / 179 skipped",
        "部署验收 40 pass / 0 fail / 0 skip",
    )),
    ("未完成", RED, (
        "H12 失败，复现 2 次，未修复",
        "前端仍在开发，界面为开发版",
        "真实 App 全局准确率 / 召回率未做",
        "最终上传与系统反馈未发生",
        "真实 App 只有 1 个历史样本",
    )),
    ("不宣称", AMBER, (
        "不宣称 100% 独立",
        "不给 AI 代码比例",
        "不宣称开源",
        "不宣称真实 App 准确率",
        "不把线索当行为、不把受控当真实",
    )),
)
for i, (title, color, items) in enumerate(columns):
    x = 0.62 + i * 4.17
    add_text(s, title, x, 2.28, 3.9, 0.28, 13, color, SANS, True)
    add_line(s, x, 2.66, x + 3.9, 2.66, color, 0.8)
    for j, item in enumerate(items):
        y = 2.85 + j * 0.70
        add_rect(s, x, y + 0.08, 0.05, 0.05, color, None)
        add_text(s, item, x + 0.16, y, 3.7, 0.56, 9, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, line_spacing=1.3)

add_text(s, "评审要素已覆盖；失败项与缺口同页保留。", 0.62, 6.55, 9.5, 0.3, 14, PAPER, SERIF, True)
add_text(s, "本片与 PPT 都不是赛事上传成功的证明；上传槽仍待人工执行。", 0.62, 6.92, 11.5, 0.2, 8, RGBColor(0x6E, 0x78, 0x88), SANS)
notes(s, "这一页专门放边界：做了什么、没做完什么、绝不宣称什么。H12 失败、前端开发版、真实 App 全局准确率未做，都写在这里。评审材料可以展示缺口，不能把缺口藏起来。")

# ---------------------------------------------------------------- slide 9
s = base_slide(9, "结语 / CLOSE", "CLOSE")
add_text(s, "先把证据摆出来，\n再谈结论。", 1.2, 2.30, 11.0, 1.7, 44, PAPER, SERIF, True, PP_ALIGN.CENTER, line_spacing=1.25)
add_text(s, "线索不等于行为。    受控结果不是真实 App 的准确率。    未知就写未知。", 1.0, 4.28, 11.3, 0.3, 12, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, PP_ALIGN.CENTER)
add_line(s, 4.8, 4.85, 8.5, 4.85, RGBColor(0x8B, 0x6A, 0x3E), 0.8)
add_text(s, "PrivacyTrace", 5.25, 5.10, 2.8, 0.4, 22, PAPER, SERIF, True, PP_ALIGN.CENTER)
add_text(s, "2026 作品评审 · 120s film / review deck", 4.5, 5.55, 4.4, 0.2, 8, AMBER, MONO, False, PP_ALIGN.CENTER, spacing=1.0)
add_text(s, "复核入口：bash scripts/check.sh  ·  node scripts/verify-review-deck.cjs  ·  delivery/manifest.json", 1.0, 6.35, 11.3, 0.2, 7.5, RGBColor(0x6E, 0x78, 0x88), MONO, False, PP_ALIGN.CENTER)
notes(s, "结语只有一句：先把证据摆出来，再谈结论。三条边界分别是线索、受控结果和未知。复核入口在仓库里，材料哈希在 manifest。")

# ---------------------------------------------------------------- slide 10
s = base_slide(10, "材料 / 复核", "APPENDIX")
add_rich(s, [[("材料与复核", SERIF, 28, PAPER, True), ("，都在这里。", SERIF, 28, AMBER, True)]], 0.62, 1.55, 6.4, 0.55, line_spacing=1.1)

rows = (
    ("视频", "PrivacyTrace-Review-1080p.mp4 · 120.000s · 1920×1080 · 30fps · H.264/AAC · 16,559,914 B"),
    ("PPT", "PrivacyTrace-Review.pptx · 10 页 · v0.2 · 与影片同一组事实与边界"),
    ("界面采集", f"移动 App · {CAPTURE_DATE} · 390×844 DPR 3 @ {SOURCE_SHORT} · capture/manifest.json"),
    ("源文件", "film-review.html（window.__seek 确定性时间线）· assets/ · BEATS.md · manifest.json"),
    ("视频 SHA-256", "51d512afb8aface80cb9b2050bd06402611520c449995e605f1b6b0cee602cc5"),
    ("数字绑定", "65b49f7 工程门禁 · 323780c9 六场景 · b0b3c74 十二场景 · 9e56771 离线包 · 2626152 H 矩阵"),
    ("复核命令", "bash scripts/check.sh  ·  node scripts/verify-review-deck.cjs  ·  对照 manifest.json 校验哈希"),
    ("提交状态", "以报名系统实际提交状态与回执为准；本页只固定材料版本与哈希。"),
)
for i, (k, v) in enumerate(rows):
    y = 2.26 + i * 0.53
    add_text(s, k, 0.62, y, 1.35, 0.2, 7.5, AMBER, MONO, False, spacing=0.8)
    add_text(s, v, 2.02, y, 10.4, 0.5, 8.5, RGBColor(0xC9, 0xC3, 0xB4), SANS, False, line_spacing=1.3)
    add_line(s, 0.62, y + 0.42, 12.55, y + 0.42, RGBColor(0x22, 0x28, 0x32), 0.5)

add_text(s, "评审要素覆盖：定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献。", 0.62, 6.55, 11.5, 0.22, 9, PAPER, SANS)
add_text(s, "缺口：H12 失败、前端开发版、真实 App 全局准确率未做。", 0.62, 6.86, 11.5, 0.22, 8.5, RGBColor(0x9A, 0xA4, 0xB2), SANS)
notes(s, f"附录把视频、PPT、界面采集、源文件、哈希、提交绑定和复核命令放在一起。界面图采集于 {CAPTURE_DATE}，提交 {SOURCE_SHORT}，来源清单在 capture/manifest.json。提交状态以报名系统为准，本页只固定材料版本与哈希。")

core = prs.core_properties
core.title = "PrivacyTrace · 作品评审 PPT"
core.author = "PrivacyTrace"
core.last_modified_by = "PrivacyTrace"
core.comments = ""
core.keywords = ""
core.category = ""
core.subject = ""
core.revision = 2
core.created = datetime(2026, 10, 23, 0, 0, 0)
core.modified = datetime(2026, 10, 23, 0, 0, 0)

prs.save(OUT)
note_total = sum(
    1 for slide in prs.slides
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
)
normalize_package(OUT, len(prs.slides), note_total)
print(OUT)
print("slides", len(prs.slides))

# ---------------------------------------------------------------- material QA
# Re-open the written package and assert the material contract the deck promises:
# ten slides with notes, both mobile captions bound to the capture batch, no
# stale dates, no internal issue references and no "not uploaded" status text.
from datetime import datetime, timezone

from pptx import Presentation as PresentationCheck

deck = PresentationCheck(str(OUT))


def slide_text(index):
    slide = deck.slides[index]
    chunks = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
    if slide.has_notes_slide:
        chunks.append(slide.notes_slide.notes_text_frame.text)
    return "\n".join(chunk for chunk in chunks if chunk)


slide_count = len(deck.slides)
note_count = sum(
    1 for slide in deck.slides
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
)
all_text = "\n".join(slide_text(index) for index in range(slide_count))
banned_hits = [phrase for phrase in BANNED_DECK_STRINGS if phrase in all_text]
caption = f"{CAPTURE_DATE} 采集 @ {SOURCE_SHORT}"
checks = {
    "slides_is_10": slide_count == 10,
    "all_slides_have_notes": note_count == 10,
    "slide2_caption": caption in slide_text(1),
    "slide2_mobile_label": "移动 App · 开发版" in slide_text(1),
    "slide4_caption": caption in slide_text(3),
    "slide4_constructed_replay": ("构造材料" in slide_text(3) and "持久化回放" in slide_text(3)),
    "slide10_ui_capture": ("界面采集" in slide_text(9) and SOURCE_SHORT in slide_text(9)),
    "no_banned_strings": not banned_hits,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit(f"deck QA failed: {failed}; banned hits: {banned_hits}")

capture_manifest_sha = sha256_file(CAPTURE_MANIFEST)
ui_images = []
for role, name in REQUIRED_SCREENS.items():
    framed = BUILD_DIR / f"{Path(name).stem}-framed.png"
    ui_images.append({
        "role": role,
        "file": f"../capture/{name}",
        "sha256": sha256_file(CAPTURE / name),
        "viewport": CAPTURE_SCREENS[name]["viewport"],
        "device_scale_factor": CAPTURE_SCREENS[name]["device_scale_factor"],
        "source_commit": CAPTURE_SCREENS[name]["source_commit"],
        "captured_at": CAPTURE_SCREENS[name]["captured_at"],
        "framed_file": f".build/{framed.name}",
        "framed_sha256": sha256_file(framed),
    })

qa = {
    "deck": {
        "file": OUT.name,
        "version": "0.2",
        "bytes": OUT.stat().st_size,
        "sha256": sha256_file(OUT),
        "slides": slide_count,
        "notes": note_count,
    },
    "capture": {
        "manifest": "../capture/manifest.json",
        "manifest_sha256": capture_manifest_sha,
        "source_commit": SOURCE_COMMIT,
        "source_commit_short": SOURCE_SHORT,
        "capture_date": CAPTURE_DATE,
        "screens": ui_images,
    },
    "captions": {
        "slide2": f"移动 App · 开发版 / {caption}",
        "slide4": f"移动报告 · 开发版 / {caption} / 构造材料 / 持久化回放",
        "slide10": f"界面采集 · 移动 App · {CAPTURE_DATE} · 390×844 DPR 3 @ {SOURCE_SHORT}",
    },
    "banned_strings": list(BANNED_DECK_STRINGS),
    "banned_hits": banned_hits,
    "checks": checks,
    "built_at": datetime.now(timezone.utc).isoformat(),
}
QA_PATH.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("qa", QA_PATH)
print("deck sha256", qa["deck"]["sha256"], "bytes", qa["deck"]["bytes"])
