"""하이쿠 카드 5장(1080x1350, 4:5)을 렌더링한다.

- 한글/영문: Pretendard (fonts/Pretendard-{Bold,Regular,Light}.otf|ttf). 없으면 Noto Sans CJK KR로 대체.
- 일본어(가나/한자): Noto Serif CJK JP.
- 배경: backgrounds/<season>/ 또는 backgrounds/any/ 의 사진. 없으면 계절 팔레트로 자동 생성.
"""
from __future__ import annotations

import hashlib
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .store import ROOT, SEASON_KO

W, H = 1080, 1350
TEXT = (246, 240, 231)
ACCENT = (236, 200, 140)
SUB = (208, 199, 186)
NOTO = Path("/usr/share/fonts/opentype/noto")

PALETTES = {  # (위, 아래, 글로우)
    "autumn": ((92, 56, 38), (212, 128, 66), (255, 214, 150)),
    "winter": ((38, 50, 70), (128, 150, 176), (232, 240, 250)),
    "spring": ((96, 70, 82), (226, 170, 170), (255, 236, 224)),
    "summer": ((30, 76, 70), (100, 170, 140), (236, 250, 210)),
}

# ───────────────────────── 폰트 ─────────────────────────


def _ttc(path: Path, size: int, tag: str) -> ImageFont.FreeTypeFont:
    for i in range(10):
        try:
            f = ImageFont.truetype(str(path), size, index=i)
        except OSError:
            break
        if tag in " ".join(f.getname()):
            return f
    return ImageFont.truetype(str(path), size)


@lru_cache(maxsize=None)
def kr_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for ext in ("otf", "ttf"):
        p = ROOT / "fonts" / f"Pretendard-{weight}.{ext}"
        if p.exists():
            return ImageFont.truetype(str(p), size)
    for w in (weight, "Regular"):
        p = NOTO / f"NotoSansCJK-{w}.ttc"
        if p.exists():
            return _ttc(p, size, "KR")
    raise RuntimeError("한글 폰트를 찾을 수 없습니다. fonts/ 폴더에 Pretendard-*.otf 를 넣어주세요.")


@lru_cache(maxsize=None)
def jp_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (
        ROOT / "fonts" / f"NotoSerifJP-{weight}.otf",
        NOTO / f"NotoSerifCJK-{weight}.ttc",
        NOTO / "NotoSerifCJK-Bold.ttc",
        NOTO / "NotoSerifCJK-Regular.ttc",
        NOTO / "NotoSansCJK-Regular.ttc",
    ):
        if p.exists():
            return ImageFont.truetype(str(p), size) if p.suffix == ".otf" else _ttc(p, size, "JP")
    raise RuntimeError("일본어 폰트를 찾을 수 없습니다. fonts-noto-cjk 를 설치하세요.")


def _is_jp(ch: str) -> bool:
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0x4E00 <= o <= 0x9FFF
            or 0x3000 <= o <= 0x303F or 0xFF66 <= o <= 0xFF9F)


def _runs(text: str) -> list[list]:
    out: list[list] = []
    for ch in text:
        jp = _is_jp(ch)
        if out and out[-1][0] == jp:
            out[-1][1] += ch
        else:
            out.append([jp, ch])
    return out


def _font_for(jp: bool, weight: str, size: int) -> ImageFont.FreeTypeFont:
    # "Black" = 포스터 스타일의 묵직한 제목체: 일본어는 Noto Serif Black(명조), 한글은 Pretendard Bold
    if jp:
        return jp_font(weight if weight in ("Bold", "Black") else "Regular", size)
    return kr_font("Bold" if weight == "Black" else weight, size)


# ───────────────────────── 텍스트 ─────────────────────────


def text_w(text: str, weight: str, size: int, tracking: int = 0) -> float:
    w = sum(_font_for(jp, weight, size).getlength(s) for jp, s in _runs(text))
    return w + tracking * max(len(text) - 1, 0)


def draw_text(d, x, y, text, weight, size, fill, align="center", tracking=0):
    """y는 기준선(baseline). 한글·일본어 폰트가 섞여도 같은 줄에 맞춘다."""
    w = text_w(text, weight, size, tracking)
    cx = x - w / 2 if align == "center" else x if align == "left" else x - w
    for jp, s in _runs(text):
        f = _font_for(jp, weight, size)
        if tracking:
            for ch in s:
                d.text((cx, y), ch, font=f, fill=fill, anchor="ls")
                cx += f.getlength(ch) + tracking
        else:
            d.text((cx, y), s, font=f, fill=fill, anchor="ls")
            cx += f.getlength(s)


def wrap(text: str, weight: str, size: int, max_w: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        trial = word if not cur else f"{cur} {word}"
        if text_w(trial, weight, size) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while text_w(cur, weight, size) > max_w:
            k = len(cur)
            while k > 1 and text_w(cur[:k], weight, size) > max_w:
                k -= 1
            lines.append(cur[:k])
            cur = cur[k:]
    if cur:
        lines.append(cur)
    return lines


def draw_vertical(d, lines, cx, top, size, step, col_gap, fill):
    """일본어 세로쓰기 — 오른쪽 열부터 왼쪽으로 읽는다."""
    n = len(lines)
    f = jp_font("Regular", size)
    for ci, line in enumerate(lines):
        x = cx + (n - 1) / 2 * col_gap - ci * col_gap
        for ri, ch in enumerate(line):
            d.text((x, top + ri * step), ch, font=f, fill=fill, anchor="mt")


# ───────────────────────── 배경 ─────────────────────────


def _cover_crop(im: Image.Image) -> Image.Image:
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((l, t, l + W, t + H))


def _procedural(season: str, seed: str) -> Image.Image:
    rng = random.Random(seed)
    top, bot, glow = PALETTES.get(season, PALETTES["autumn"])
    grad = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), bot), Image.new("RGB", (W, H), top), grad)

    g = Image.new("L", (W, H), 0)
    cx, cy, r = rng.randint(280, 800), rng.randint(260, 620), rng.randint(240, 340)
    ImageDraw.Draw(g).ellipse((cx - r, cy - r, cx + r, cy + r), fill=200)
    g = g.filter(ImageFilter.GaussianBlur(140))
    img = Image.composite(Image.new("RGB", (W, H), glow), img, g)

    m = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(m)
    for _ in range(5):
        x, y = rng.randint(-200, 800), rng.randint(700, 1250)
        md.ellipse((x, y, x + rng.randint(600, 1100), y + rng.randint(60, 140)), fill=rng.randint(40, 80))
    m = m.filter(ImageFilter.GaussianBlur(40)).point(lambda p: int(p * 0.5))
    img = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)), img, m)

    img = Image.blend(img, Image.effect_noise((W, H), 24).convert("RGB"), 0.06)
    v = Image.radial_gradient("L").resize((W, H)).point(lambda p: int(p * 0.35))
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, v)


def make_bg(post: dict) -> Image.Image:
    season = post.get("season", "any")
    photos: list[Path] = []
    for folder in (ROOT / "backgrounds" / season, ROOT / "backgrounds" / "any"):
        if folder.is_dir():
            photos += [p for p in sorted(folder.iterdir())
                       if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if photos:
        idx = int(hashlib.md5(post["id"].encode()).hexdigest(), 16) % len(photos)
        return _cover_crop(Image.open(photos[idx]).convert("RGB"))
    return _procedural(season, post["id"])


def _darken(img: Image.Image, top_a: float, bottom_a: float) -> Image.Image:
    mask = Image.linear_gradient("L").resize((W, H)).point(
        lambda p: int((top_a + (bottom_a - top_a) * p / 255) * 255))
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, mask)


def _chrome(img: Image.Image, page: int, total: int, handle: str) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((44, 44, W - 44, H - 44), outline=ACCENT + (70,), width=2)
    draw_text(d, 96, H - 86, f"{page:02d} / {total:02d}", "Light", 24, SUB + (200,), align="left", tracking=3)
    if handle:
        draw_text(d, W - 96, H - 86, handle, "Light", 24, SUB + (200,), align="right", tracking=2)


# ───────────────────────── 슬라이드 ─────────────────────────


def _slide_cover(bg, p):
    img = _darken(bg, 0.10, 0.52)
    d = ImageDraw.Draw(img, "RGBA")
    s = SEASON_KO.get(p.get("season", "any"), "")
    draw_text(d, W / 2, 200, "오늘의 하이쿠" + (f" · {s}" if s else ""), "Light", 30, ACCENT, tracking=6)
    lines = wrap(p["cover_ko"], "Bold", 72, 820)
    lh = 118
    y = (H - len(lines) * lh) / 2 + 90
    for ln in lines:
        draw_text(d, W / 2, y, ln, "Bold", 72, TEXT)
        y += lh
    d.line((W / 2 - 40, y + 10, W / 2 + 40, y + 10), fill=ACCENT + (200,), width=2)
    draw_text(d, W / 2, y + 80, "俳句", "Light", 30, SUB, tracking=10)
    return img


def _slide_original(bg, p):
    img = _darken(bg, 0.36, 0.50)
    d = ImageDraw.Draw(img, "RGBA")
    draw_text(d, W / 2, 190, "原文", "Light", 30, ACCENT, tracking=10)
    size, step, gap = 92, 108, 150
    n = max(len(l) for l in p["original"])
    block = (n - 1) * step + size
    top = 250 + (700 - block) / 2
    draw_vertical(d, p["original"], W / 2, top, size, step, gap, TEXT)
    y = 1020
    for ln in p["romaji"]:
        draw_text(d, W / 2, y, ln, "Light", 30, SUB, tracking=2)
        y += 50
    return img


def _slide_translation(bg, p):
    img = _darken(bg, 0.36, 0.50)
    d = ImageDraw.Draw(img, "RGBA")
    lines = p["translation_ko"]
    lh = 104
    y = (H - len(lines) * lh) / 2 + 20
    for ln in lines:
        draw_text(d, W / 2, y, ln, "Regular", 64, TEXT)
        y += lh
    d.line((W / 2 - 40, y + 10, W / 2 + 40, y + 10), fill=ACCENT + (200,), width=2)
    draw_text(d, W / 2, y + 80, f"— {p['poet_ko']} ({p['poet_ja']})", "Light", 36, ACCENT)
    return img


def _slide_commentary(bg, p):
    img = _darken(bg, 0.42, 0.54)
    d = ImageDraw.Draw(img, "RGBA")
    tag =f"계절어 · {p['kigo_ko']} ({p['kigo_ja']})"
    pw = text_w(tag, "Regular", 30) + 64
    d.rounded_rectangle((W / 2 - pw / 2, 170, W / 2 + pw / 2, 238), radius=34,
                        outline=ACCENT + (210,), width=2)
    draw_text(d, W / 2, 215, tag, "Regular", 30, ACCENT)
    for size in range(42, 31, -2):
        lh = round(size * 1.75)
        wrapped = [wrap(t, "Regular", size, 860) for t in p["commentary_ko"]]
        total = sum(len(w) * lh for w in wrapped) + 40 * (len(wrapped) - 1)
        if 330 + total <= 1140:
            break
    y = 340 + max(0, (1140 - 340 - total)) * 0.4  # 짧은 해설은 중앙 쪽으로
    for para in wrapped:
        for ln in para:
            draw_text(d, 110, y, ln, "Regular", size, TEXT, align="left")
            y += lh
        y += 40
    return img


def _slide_closing(bg, p, handle):
    img = _darken(bg, 0.36, 0.52)
    d = ImageDraw.Draw(img, "RGBA")
    lines = wrap(p["question_ko"], "Bold", 58, 820)
    lh = 96
    y = (H - len(lines) * lh) / 2 - 30
    for ln in lines:
        draw_text(d, W / 2, y, ln, "Bold", 58, TEXT)
        y += lh
    d.line((W / 2 - 40, y + 10, W / 2 + 40, y + 10), fill=ACCENT + (200,), width=2)
    draw_text(d, W / 2, y + 90, "마음이 헛헛할 때, 저장해두고 꺼내 보세요", "Light", 32, SUB)
    draw_text(d, W / 2, y + 144, "함께 읽고 싶은 사람에게 보내 보세요", "Light", 32, SUB)
    if handle:
        draw_text(d, W / 2, y + 250, handle, "Regular", 34, ACCENT, tracking=2)
    return img


def _render_classic(post: dict, out_dir: Path, cfg: dict) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    handle = cfg.get("handle", "")
    bg = make_bg(post)
    soft = bg.filter(ImageFilter.GaussianBlur(5))  # 글자 슬라이드는 살짝 흐리게
    slides = [
        _slide_cover(bg, post),
        _slide_original(soft, post),
        _slide_translation(soft, post),
        _slide_commentary(soft, post),
        _slide_closing(soft, post, handle),
    ]
    paths = []
    for i, img in enumerate(slides, 1):
        _chrome(img, i, len(slides), handle)
        path = out_dir / f"slide_{i}.jpg"
        img.convert("RGB").save(path, "JPEG", quality=92, subsampling=0)
        paths.append(path)
    return paths


# ═════════════ POSTER 스타일 ═════════════
# 원색(빨강·검정·종이색) 대비 + 한 줄마다 하이라이트 박스 + 묵직한 명조 + 기하학 블록 + 거친 그레인.
RED = (220, 42, 26)
INK = (24, 22, 22)
PAPER = (250, 247, 241)


def _flat(color, grain=0.06):
    img = Image.new("RGB", (W, H), color)
    return Image.blend(img, Image.effect_noise((W, H), 30).convert("RGB"), grain)


def _box_h(size: int) -> int:
    return round(size * 1.08) + 2 * round(size * 0.06)


def draw_boxed(d, lines, x, y, size, weight, fg, bg, gap=4, pad_x=None):
    """줄마다 글자 폭에 딱 맞는 박스를 깔고 쌓는다(왼쪽 정렬, 오른쪽은 들쭉날쭉). 끝 y를 반환."""
    pad_x = round(size * 0.2) if pad_x is None else pad_x
    pad_y = round(size * 0.06)
    bh = _box_h(size)
    for ln in lines:
        bw = text_w(ln, weight, size) + 2 * pad_x
        d.rectangle((x, y, x + bw, y + bh), fill=bg)
        draw_text(d, x + pad_x, y + pad_y + round(size * 0.9), ln, weight, size, fg, align="left")
        y += bh + gap
    return y


def _stack_h(n: int, size: int, gap: int = 4) -> int:
    return n * (_box_h(size) + gap)


def _blocks(img: Image.Image, seed: str) -> None:
    """가장자리에 붙는 빨강/검정 기하학 블록 (60px 격자에 맞춤)."""
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    snap = lambda v: int(round(v / 60) * 60)
    specs = []
    for _ in range(2):
        w, h = snap(rng.randint(240, 600)), snap(rng.randint(60, 180))
        x = snap(rng.randint(0, W - w))
        specs.append((x, 0, x + w, h))
        w, h = snap(rng.randint(240, 600)), snap(rng.randint(60, 180))
        x = snap(rng.randint(0, W - w))
        specs.append((x, H - h, x + w, H))
        h, w = snap(rng.randint(240, 600)), snap(rng.randint(60, 140))
        y = snap(rng.randint(0, H - h))
        specs.append((0, y, w, y + h))
        h, w = snap(rng.randint(240, 600)), snap(rng.randint(60, 140))
        y = snap(rng.randint(0, H - h))
        specs.append((W - w, y, W, y + h))
    rng.shuffle(specs)
    for i, s in enumerate(specs):
        d.rectangle(s, fill=(RED, INK)[i % 2])


def _chrome_poster(img: Image.Image, page: int, total: int, handle: str, fg) -> None:
    d = ImageDraw.Draw(img)
    draw_text(d, 96, H - 80, f"{page:02d} / {total:02d}", "Regular", 24, fg, align="left", tracking=3)
    if handle:
        draw_text(d, W - 96, H - 80, handle, "Regular", 24, fg, align="right", tracking=2)


def _fit(lines, weight, max_w, start, stop=60, step=4):
    for s in range(start, stop, -step):
        if max(text_w(l, weight, s) for l in lines) + 2 * round(s * 0.2) <= max_w:
            return s
    return stop


def _p_cover(p):
    img = _flat(RED)
    d = ImageDraw.Draw(img)
    size = 78
    lines = wrap(p["cover_ko"], "Black", size, 800)
    y = (H - _stack_h(len(lines) + 1, size)) / 2 - 20
    s = SEASON_KO.get(p.get("season", "any"), "")
    draw_boxed(d, ["오늘의 하이쿠" + (f" · {s}" if s else "")], 100, 150, 30, "Black", PAPER, INK)
    y = draw_boxed(d, lines, 100, y, size, "Black", INK, PAPER)
    draw_boxed(d, ["그리고,"], 100, y, size, "Black", INK, PAPER)  # 다음 장으로 넘기게 하는 미완의 한 줄
    return img


def _p_original(p):
    img = _flat(RED)
    d = ImageDraw.Draw(img)
    size = _fit(p["original"], "Black", 880, 130)
    rsize = 30
    total = 60 + _stack_h(len(p["original"]), size) + 40 + _stack_h(len(p["romaji"]), rsize)
    y = max(250, (H - total) / 2 + 20)
    draw_boxed(d, ["原文"], 100, y - 70, 30, "Black", PAPER, INK)
    y = draw_boxed(d, p["original"], 100, y, size, "Black", INK, PAPER)
    draw_boxed(d, p["romaji"], 100, y + 40, rsize, "Regular", PAPER, INK)
    return img


def _p_translation(p):
    img = _flat(PAPER, grain=0.04)
    _blocks(img, p["id"])
    d = ImageDraw.Draw(img)
    lines = p["translation_ko"]
    size = _fit(lines, "Black", 860, 76)
    pad = round(size * 0.2)
    mw = max(text_w(l, "Black", size) for l in lines) + 2 * pad
    x = (W - mw) / 2
    total = _stack_h(len(lines), size) + 30 + _box_h(34)
    y = (H - total) / 2
    y = draw_boxed(d, lines, x, y, size, "Black", PAPER, INK)
    draw_boxed(d, [f"{p['poet_ko']} · {p['poet_ja']}"], x, y + 26, 34, "Black", PAPER, RED)
    return img


def _p_commentary(p):
    img = _flat(INK)
    d = ImageDraw.Draw(img)
    d.rectangle((W - 160, 0, W, 140), fill=RED)
    draw_boxed(d, [f"계절어 · {p['kigo_ko']} {p['kigo_ja']}"], 110, 190, 32, "Black", PAPER, RED)
    for size in range(42, 31, -2):
        lh = round(size * 1.75)
        wrapped = [wrap(t, "Regular", size, 860) for t in p["commentary_ko"]]
        total = sum(len(w) * lh for w in wrapped) + 40 * (len(wrapped) - 1)
        if 360 + total <= 1140:
            break
    y = 360 + max(0, (1140 - 360 - total)) * 0.4
    for para in wrapped:
        for ln in para:
            draw_text(d, 110, y, ln, "Regular", size, PAPER, align="left")
            y += lh
        y += 40
    return img


def _p_closing(p, handle):
    img = _flat(RED)
    d = ImageDraw.Draw(img)
    size = 66
    q = wrap(p["question_ko"], "Black", size, 800)
    notes = ["마음이 헛헛할 때, 저장해두고 꺼내 보세요", "함께 읽고 싶은 사람에게 보내 보세요"]
    total = _stack_h(len(q), size) + 50 + _stack_h(2, 32) + (90 if handle else 0)
    y = (H - total) / 2
    y = draw_boxed(d, q, 100, y, size, "Black", INK, PAPER)
    y = draw_boxed(d, notes, 100, y + 50, 32, "Regular", PAPER, INK)
    if handle:
        draw_boxed(d, [handle], 100, y + 40, 34, "Black", RED, PAPER)
    return img


def _render_poster(post: dict, out_dir: Path, cfg: dict) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    handle = cfg.get("handle", "")
    slides = [(_p_cover(post), INK), (_p_original(post), INK), (_p_translation(post), INK),
              (_p_commentary(post), PAPER), (_p_closing(post, handle), INK)]
    paths = []
    for i, (img, fg) in enumerate(slides, 1):
        _chrome_poster(img, i, len(slides), handle, fg)
        path = out_dir / f"slide_{i}.jpg"
        img.save(path, "JPEG", quality=92, subsampling=0)
        paths.append(path)
    return paths


def render_post(post: dict, out_dir: Path, cfg: dict) -> list[Path]:
    """style: 'poster'(기본, 원색·하이라이트 박스) | 'classic'(어두운 톤+사진 배경). 항목별 post['style']로도 지정 가능."""
    style = post.get("style") or cfg.get("style", "poster")
    return (_render_poster if style == "poster" else _render_classic)(post, out_dir, cfg)
