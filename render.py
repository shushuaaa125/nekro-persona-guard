"""人设哨兵 - 日报卡片渲染（双主题 + 头像）。"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_HERE = Path(__file__).parent
_FONT_DIR = _HERE / "fonts"

W = 760
PAD = 40

THEMES = {
    "dark": {
        "bg_top": (9, 13, 18),
        "bg_bottom": (15, 23, 30),
        "glow": (26, 44, 56),
        "card": (18, 26, 33),
        "card_alt": (16, 23, 29),
        "line": (34, 48, 58),
        "text": (226, 236, 242),
        "dim": (122, 143, 154),
        "accent": (110, 178, 200),
        "warn": (255, 200, 97),
        "bad": (255, 139, 139),
        "good": (140, 220, 160),
        "track": (34, 46, 56),
    },
    "light": {
        "bg_top": (250, 252, 253),
        "bg_bottom": (233, 240, 244),
        "glow": (210, 226, 234),
        "card": (255, 255, 255),
        "card_alt": (245, 249, 251),
        "line": (214, 226, 233),
        "text": (27, 42, 51),
        "dim": (92, 114, 126),
        "accent": (42, 118, 140),
        "warn": (166, 100, 0),
        "bad": (183, 50, 40),
        "good": (24, 112, 66),
        "track": (222, 232, 238),
    },
}

FAMILY_LABEL = {
    "gemini": ("Gemini", "Gem", (86, 130, 190)),
    "deepseek": ("DeepSeek", "DS", (52, 132, 168)),
    "claude": ("Claude", "Claude", (180, 110, 60)),
    "gpt": ("GPT", "GPT", (40, 140, 100)),
    "qwen": ("Qwen", "Qwen", (120, 90, 180)),
    "glm": ("GLM", "GLM", (60, 140, 130)),
    "doubao": ("豆包", "豆包", (190, 95, 130)),
    "kimi": ("Kimi", "Kimi", (90, 120, 200)),
    "grok": ("Grok", "Grok", (80, 80, 90)),
    "ernie": ("文心", "文心", (60, 110, 200)),
    "hunyuan": ("混元", "混元", (70, 150, 190)),
    "spark": ("星火", "星火", (200, 130, 60)),
    "o1": ("o1", "o1", (110, 110, 130)),
    "generic": ("未识别", "?", (130, 140, 150)),
}

_AVATAR_CACHE: Optional[Image.Image] = None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc"
    path = _FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    cands = [
        "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for cand in cands:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


TITLE_FONTS = {
    "smiley": "SmileySans-Oblique.ttf",
    "nuomi": "HYNuoMiTuanW.ttf",
    "kuaile": "ZCOOLKuaiLe-Regular.ttf",
}


def _title_font(size: int, mode: str = "smiley") -> ImageFont.FreeTypeFont:
    """标题字体：按 mode 找文件，找不到退回 Noto 粗体。"""
    mode = (mode or "smiley").lower()
    if mode == "nuomi":
        size += 5
    fname = TITLE_FONTS.get(mode)
    if fname:
        for d in (_FONT_DIR, Path("C:/Windows/Fonts")):
            cand = d / fname
            if cand.exists():
                try:
                    return ImageFont.truetype(str(cand), size)
                except Exception:
                    pass
    return _font(size, bold=True)


def _avatar(url: str = "", local: Path | None = None) -> Optional[Image.Image]:
    global _AVATAR_CACHE
    if _AVATAR_CACHE is not None:
        return _AVATAR_CACHE
    try:
        if local and Path(local).exists():
            _AVATAR_CACHE = Image.open(local).convert("RGB")
            return _AVATAR_CACHE
        if url:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:  # noqa: S310
                _AVATAR_CACHE = Image.open(io.BytesIO(resp.read())).convert("RGB")
                return _AVATAR_CACHE
    except Exception:
        return None
    return None


def _circle(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


DIALOGUE_SEGMENTS = [(0.62, 0.45, 0.40), (0.80, 0.62, 0.42), (0.45, 0.68, 0.78), (0.42, 0.82, 0.66)]
HUMAN_SEGMENTS = [(0.42, 0.48, 0.56), (0.56, 0.62, 0.70), (0.86, 0.72, 0.52), (0.95, 0.68, 0.40)]
DIALOGUE_WORDS = ["小说感", "偏小说感", "偏对话感", "对话感"]
HUMAN_WORDS = ["人机味", "偏人机味", "偏活人感", "活人感"]
DIALOGUE_LABELS = ["小说感", "偏小说感", "偏对话感", "对话感"]


def dialogue_band(score: float) -> str:
    # 与四段刻度严格对齐：0-25 小说感 / 25-50 偏小说感 / 50-75 偏对话感 / 75-100 对话感
    if score >= 75:
        return DIALOGUE_LABELS[3]
    if score >= 50:
        return DIALOGUE_LABELS[2]
    if score >= 25:
        return DIALOGUE_LABELS[1]
    return DIALOGUE_LABELS[0]


def _gradient_bar(img, x, y, w, h, segs, radius=5, edge_fade=None):
    """连续渐变条：圆角 + 两端向背景羽化。"""
    w = max(2, int(w))
    cols = [(int(255 * c[0]), int(255 * c[1]), int(255 * c[2])) for c in segs]
    bar = Image.new("RGB", (w, h), cols[0])
    bd = ImageDraw.Draw(bar)
    for i in range(w):
        t_ = i / (w - 1)
        if t_ < 0.33:
            a, b, u = cols[0], cols[1], t_ / 0.33
        elif t_ < 0.66:
            a, b, u = cols[1], cols[2], (t_ - 0.33) / 0.33
        else:
            a, b, u = cols[2], cols[3], (t_ - 0.66) / 0.34
        col = tuple(int(a[k] + (b[k] - a[k]) * u) for k in range(3))
        if edge_fade:
            bg = edge_fade
            fade = 10
            if i < fade:
                k = i / fade
                col = tuple(int(bg[j] + (col[j] - bg[j]) * k) for j in range(3))
            elif i > w - 1 - fade:
                k = (w - 1 - i) / fade
                col = tuple(int(bg[j] + (col[j] - bg[j]) * k) for j in range(3))
        bd.line([(i, 0), (i, h)], fill=col)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    img.paste(bar, (int(x), int(y)), mask)


def band_scale(d, x: int, y: int, w: int, score: float, words, segs, t: Dict[str, Any], font,
               img=None) -> None:
    """渐变刻度 + 光晕圆钮 + 高亮当前区间。"""
    if img is None:
        img = getattr(d, "_image", None)
    h = 12
    if img is not None:
        _gradient_bar(img, x, y, w, h, segs, radius=6, edge_fade=t["card"])
    else:
        for i in range(4):
            seg_w = w / 4
            r, g, b = segs[i]
            d.rounded_rectangle((x + i * seg_w, y, x + (i + 1) * seg_w - 2, y + h), radius=6,
                                fill=(int(255 * r), int(255 * g), int(255 * b)))

    idx = 3 if score >= 75 else (2 if score >= 50 else (1 if score >= 25 else 0))
    active_seg_w = w / 4
    for i, label in enumerate(words):
        d.text((x + active_seg_w * i + active_seg_w / 2 - 1, y + h + 8), label,
               font=font, fill=t["text"] if i == idx else t["dim"], anchor="ma")

    pos = x + w * max(0.03, min(0.97, score / 100.0))
    cy = y + h / 2
    d.ellipse((pos - 6, cy - 6, pos + 6, cy + 6), fill=t["text"], outline=(26, 34, 40), width=2)
    vx = min(max(pos, x + 10), x + w - 10)
    d.text((vx, y - 15), f"{score:.0f}", font=font, fill=t["dim"], anchor="ma")


def value_scale(d, x, y, w, value, lo, hi, cuts, words, segs, t, font, target=None) -> None:
    """数值刻度：连续渐变 + 目标线 + 光晕圆钮。"""
    img = getattr(d, "_image", None)
    h = 12
    if img is not None:
        _gradient_bar(img, x, y, w, h, segs, radius=6, edge_fade=t["card"])
    else:
        bounds0 = [lo] + list(cuts) + [hi]
        for i in range(4):
            x0 = x + w * (bounds0[i] - lo) / (hi - lo)
            x1 = x + w * (bounds0[i + 1] - lo) / (hi - lo)
            r, g, b = segs[i]
            d.rounded_rectangle((x0, y, x1 - 2, y + h), radius=6,
                                fill=(int(255 * r), int(255 * g), int(255 * b)))

    bounds = [lo] + list(cuts) + [hi]
    for i in range(4):
        cx = (x + w * (bounds[i] - lo) / (hi - lo) + x + w * (bounds[i + 1] - lo) / (hi - lo)) / 2
        d.text((cx, y + h + 7), words[i], font=font, fill=t["dim"], anchor="ma")

    if target is not None:
        tp = x + w * max(0.02, min(0.98, (target - lo) / max(1e-6, hi - lo)))
        d.line([(tp, y - 7), (tp, y + h + 5)], fill=t["dim"], width=1)

    frac = max(0.02, min(0.98, (value - lo) / max(1e-6, hi - lo)))
    pos = x + w * frac
    cy = y + h / 2
    d.ellipse((pos - 6, cy - 6, pos + 6, cy + 6), fill=t["text"], outline=(26, 34, 40), width=2)


def value_band(value, cuts, words) -> str:
    if value < cuts[0]:
        return words[0]
    if value < cuts[1]:
        return words[1]
    if value < cuts[2]:
        return words[2]
    return words[3]


def dialogue_scale(d, x: int, y: int, w: int, score: float, t: Dict[str, Any], font) -> None:
    band_scale(d, x, y, w, score, DIALOGUE_WORDS, DIALOGUE_SEGMENTS, t, font)


def human_scale(d, x: int, y: int, w: int, score: float, t: Dict[str, Any], font) -> None:
    band_scale(d, x, y, w, score, HUMAN_WORDS, HUMAN_SEGMENTS, t, font)


def human_band(score: float) -> str:
    if score >= 75:
        return HUMAN_WORDS[3]
    if score >= 50:
        return HUMAN_WORDS[2]
    if score >= 25:
        return HUMAN_WORDS[1]
    return HUMAN_WORDS[0]


def _rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _bg(w: int, h: int, t: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGB", (w, h), t["bg_top"])
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / max(1, h - 1)
        d.line(
            [(0, y), (w, y)],
            fill=tuple(int(t["bg_top"][i] + (t["bg_bottom"][i] - t["bg_top"][i]) * k) for i in range(3)),
        )
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-w * 0.35, -h * 0.35, w * 0.55, h * 0.35], fill=t["glow"])
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    img = Image.blend(img, glow, 0.25)
    return img


def _section(d, y: int, title: str, t: Dict[str, Any], right: str = "") -> int:
    d.rounded_rectangle((PAD, y + 3, PAD + 3, y + 15), radius=2, fill=t["accent"])
    d.text((PAD + 12, y), title, font=_font(14, bold=True), fill=t["dim"])
    if right:
        d.text((W - PAD, y + 1), right, font=_font(12), fill=t["dim"], anchor="ra")
    return y + 30


def _ring(d, cx, cy, r, pct, color, track):
    d.arc([cx - r, cy - r, cx + r, cy + r], start=135, end=405, fill=track, width=9)
    if pct > 0:
        end = 135 + 270 * max(0.0, min(1.0, pct / 100))
        d.arc([cx - r, cy - r, cx + r, cy + r], start=135, end=end, fill=color, width=9)


def render_report_card(
    data: Dict[str, Any],
    out_path: Path,
    theme: str = "dark",
    avatar_url: str = "",
    avatar_path: Path | None = None,
    title_font: str = "smiley",
) -> Path:
    t = THEMES["dark"]  # 只做夜版
    chats: List[Dict[str, Any]] = data.get("chats") or []
    hits: List[Dict[str, Any]] = data.get("hits") or []
    models: List[Dict[str, Any]] = data.get("models") or []
    match: Dict[str, Any] = data.get("match") or {}
    dialects: Dict[str, Any] = data.get("dialects") or {}
    cons: Dict[str, Any] = data.get("consistency") or {}
    shadow: Dict[str, Any] = data.get("shadow") or {}
    shadow_items = shadow.get("items") or []
    shadow_n = int(shadow.get("count") or 0)
    chatcheck: Dict[str, Any] = data.get("chatcheck") or {}
    cc_items = chatcheck.get("items") or []
    cc_n = int(chatcheck.get("count") or 0)
    conflicts = cons.get("conflicts") or []

    has_match = bool(match.get("parts"))
    has_cons = bool(cons.get("ok"))

    H = 226
    H += 104
    H += 30 + max(1, len(chats)) * 44
    if models:
        H += 30 + len(models) * 36
    if has_match:
        H += 320
    if has_cons:
        H += 30 + (min(3, len(conflicts)) * 26 if conflicts else 24)
    if dialects or int(data.get("habit", 0)) > 0:
        H += 60
    H += 30 + (len(hits) * 30 if hits else 26)
    if shadow_n:
        H += 28 + min(2, len(shadow_items)) * 26
    if cc_n:
        H += 28 + min(2, len(cc_items)) * 44
    H += 54

    img = _bg(W, H, t)
    d = ImageDraw.Draw(img)

    f_title = _title_font(29, title_font)
    f_sub = _font(13)
    f_big = _font(31, bold=True)
    f_small = _font(12)
    f_row = _font(14)

    y = 34

    # ---------- 头像 + 标题 ----------
    av_size = 54
    av = _avatar(avatar_url, avatar_path)
    ax, ay = PAD, y - 6
    if av is not None:
        circ = _circle(av, av_size)
        img.paste(circ, (ax, ay), circ)
        d.ellipse((ax - 1, ay - 1, ax + av_size, ay + av_size), outline=t["accent"], width=2)
    else:
        d.ellipse((ax, ay, ax + av_size, ay + av_size), fill=t["card"], outline=t["accent"], width=2)
        d.text((ax + av_size / 2, ay + av_size / 2 - 9), "西", font=_font(20, bold=True),
               fill=t["accent"], anchor="ma")

    tx = ax + av_size + 16
    d.text((tx, y - 2), "人设哨兵", font=f_title, fill=t["text"])
    tw = d.textlength("人设哨兵", font=f_title)
    d.polygon([(tx + tw + 12, y + 6), (tx + tw + 18, y + 12), (tx + tw + 12, y + 18), (tx + tw + 6, y + 12)],
              fill=t["accent"])
    d.text((W - PAD, y), "日报", font=f_sub, fill=t["dim"], anchor="ra")

    # 模型 pill + 日期
    py = y + 34
    model_name = str(data.get("model") or "")
    fam = str(data.get("model_family") or "")
    label = FAMILY_LABEL.get(fam, ("", "", t["accent"]))[0]
    pill_txt = model_name if model_name and model_name != "unknown" else "模型未知"
    pw = d.textlength(pill_txt, font=f_small) + 26
    _rr(d, (tx, py, tx + pw, py + 24), 12, fill=t["card"], outline=t["line"])
    d.ellipse((tx + 10, py + 9, tx + 16, py + 15), fill=t["accent"])
    d.text((tx + 21, py + 4), pill_txt, font=f_small, fill=t["text"])
    if label:
        d.text((tx + pw + 10, py + 5), label, font=f_small, fill=t["dim"])
    d.text((W - PAD, py + 5), str(data.get("date", "")), font=f_sub, fill=t["dim"], anchor="ra")
    y = py + 48

    # ---------- 统计卡 ----------
    stats = [
        ("消息", str(data.get("total", 0)), t["text"], t["accent"]),
        ("人机味", str(data.get("ai", 0)), t["warn"], t["warn"]),
        ("设定冲突", str(data.get("conflict", 0)), t["bad"], t["bad"]),
        ("称呼开头", f"{data.get('address', 0)}/{data.get('total', 0)}", t["accent"], t["accent"]),
    ]
    gap = 12
    bw = (W - PAD * 2 - gap * 3) // 4
    for i, (k, v, color, bar) in enumerate(stats):
        x0 = PAD + i * (bw + gap)
        _rr(d, (x0, y, x0 + bw, y + 92), 13, fill=t["card"], outline=t["line"])
        _rr(d, (x0 + 14, y + 14, x0 + 36, y + 17), 2, fill=bar)
        d.text((x0 + 14, y + 26), k, font=f_small, fill=t["dim"])
        d.text((x0 + 14, y + 48), v, font=f_big, fill=color)
    y += 104 + 26

    # ---------- 按会话 ----------
    y = _section(d, y, "按会话统计", t, f"{len(chats)} 个会话")
    if not chats:
        d.text((PAD + 4, y + 4), "今天还没有记录", font=f_row, fill=t["dim"])
        y += 32
    for c in chats:
        total = int(c.get("total", 0)) or 0
        rate = f"{round(100 * int(c.get('address', 0)) / total)}%" if total else "—"
        _rr(d, (PAD, y, W - PAD, y + 38), 10, fill=t["card_alt"], outline=t["line"])
        name = str(c.get("name", ""))[:14]
        d.text((PAD + 14, y + 10), name, font=f_row, fill=t["text"])
        tag, _, tcolor = FAMILY_LABEL.get(str(c.get("family") or ""), ("", "", t["dim"]))
        if tag:
            nw = d.textlength(name, font=f_row)
            tw2 = d.textlength(tag, font=f_small) + 14
            _rr(d, (PAD + 22 + nw, y + 11, PAD + 22 + nw + tw2, y + 27), 8, fill=t["card"], outline=t["line"])
            d.text((PAD + 29 + nw, y + 12), tag, font=f_small, fill=tcolor)
        d.text((W - PAD - 300, y + 11), str(total), font=f_small, fill=t["dim"], anchor="ra")
        ai_n, cf_n = int(c.get("ai", 0)), int(c.get("conflict", 0))
        d.text((W - PAD - 214, y + 11), str(ai_n), font=f_small, fill=t["warn"] if ai_n else t["dim"], anchor="ra")
        d.text((W - PAD - 128, y + 11), str(cf_n), font=f_small, fill=t["bad"] if cf_n else t["dim"], anchor="ra")
        d.text((W - PAD - 14, y + 11), rate, font=f_small, fill=t["accent"], anchor="ra")
        y += 44

    # ---------- 按模型 ----------
    if models:
        y = _section(d, y, "按模型统计", t)
        for m in models:
            fam2 = str(m.get("family") or "")
            full, _, color = FAMILY_LABEL.get(fam2, (fam2, fam2, t["dim"]))
            total = int(m.get("total", 0)) or 0
            rate = f"{round(100 * int(m.get('address', 0)) / total)}%" if total else "—"
            _rr(d, (PAD, y, W - PAD, y + 32), 9, fill=t["card_alt"], outline=t["line"])
            d.ellipse((PAD + 12, y + 13, PAD + 19, y + 20), fill=color)
            d.text((PAD + 26, y + 8), full, font=f_small, fill=t["text"])
            d.text((W - PAD - 300, y + 8), str(total), font=f_small, fill=t["dim"], anchor="ra")
            ai_n, cf_n = int(m.get("ai", 0)), int(m.get("conflict", 0))
            d.text((W - PAD - 214, y + 8), str(ai_n), font=f_small, fill=t["warn"] if ai_n else t["dim"], anchor="ra")
            d.text((W - PAD - 128, y + 8), str(cf_n), font=f_small, fill=t["bad"] if cf_n else t["dim"], anchor="ra")
            d.text((W - PAD - 14, y + 8), rate, font=f_small, fill=t["accent"], anchor="ra")
            y += 36
        y += 6

    # ---------- 匹配度 ----------
    if has_match:
        y = _section(d, y, "人设匹配度", t)
        score = float(match.get("score") or 0)
        color = t["good"] if score >= 75 else (t["warn"] if score >= 55 else t["bad"])
        _rr(d, (PAD, y, W - PAD, y + 300), 13, fill=t["card"], outline=t["line"])
        cx, cy = PAD + 62, y + 59
        _ring(d, cx, cy, 34, score, color, t["track"])
        d.text((cx, cy - 14), f"{score:.0f}", font=_font(22, bold=True), fill=color, anchor="ma")
        d.text((cx, cy + 12), "/100", font=_font(10), fill=t["dim"], anchor="ma")

        parts = match.get("parts") or {}
        dialogue_val = float(parts.pop("对话感", 50))
        human_val = float(parts.pop("去人机味", 50))
        parts.pop("句式贴合", None)
        parts.pop("口头习惯", None)
        setting_val = float(parts.pop("设定一致", 100))

        d.text((PAD + 142, y + 26), "设定一致", font=_font(11), fill=t["dim"])
        sc = t["good"] if setting_val >= 75 else (t["warn"] if setting_val >= 55 else t["bad"])
        d.text((PAD + 142, y + 44), f"{setting_val:.0f}", font=_font(20, bold=True), fill=sc)

        scale_left = PAD + 128
        scale_right = W - PAD - 20

        band = dialogue_band(dialogue_val)
        d.text((PAD + 24, y + 106), "对话感", font=_font(11), fill=t["dim"])
        d.text((PAD + 64, y + 102), band, font=_font(13, bold=True), fill=t["text"])
        dialogue_scale(d, scale_left, y + 118, scale_right - scale_left, dialogue_val, t, _font(10))

        hband = human_band(human_val)
        d.text((PAD + 24, y + 152), "活人感", font=_font(11), fill=t["dim"])
        d.text((PAD + 68, y + 148), hband, font=_font(13, bold=True), fill=t["text"])
        human_scale(d, scale_left, y + 164, scale_right - scale_left, human_val, t, _font(10))

        avg_len = float(match.get("avg_len") or 26)
        tgt_len = float(match.get("target_len") or 26)
        len_cuts = [tgt_len * 0.7, tgt_len * 0.9, tgt_len * 1.2]
        len_words = ["太短", "偏短", "偏长", "太长"]
        len_segs = [(0.55, 0.62, 0.72), (0.48, 0.66, 0.78), (0.80, 0.72, 0.50), (0.88, 0.60, 0.42)]
        d.text((PAD + 24, y + 196), "句长", font=_font(11), fill=t["dim"])
        d.text((PAD + 60, y + 192), f"{avg_len:.0f} 字", font=_font(13, bold=True), fill=t["text"])
        d.text((W - PAD - 20, y + 194), f"常态 {tgt_len:.0f} 字", font=_font(10), fill=t["dim"], anchor="ra")
        value_scale(d, scale_left, y + 208, scale_right - scale_left, avg_len, 8, 60,
                    len_cuts, len_words, len_segs, t, _font(10), tgt_len)

        prate = float(match.get("particle_rate") or 50)
        tgt_p = float(match.get("target_particle") or 50)
        p_cuts = [tgt_p * 0.6, tgt_p * 0.9, tgt_p * 1.3]
        p_words = ["太素", "偏素", "偏满", "太满"]
        p_segs = [(0.50, 0.60, 0.70), (0.55, 0.68, 0.78), (0.85, 0.72, 0.48), (0.90, 0.58, 0.42)]
        d.text((PAD + 24, y + 244), "语气词", font=_font(11), fill=t["dim"])
        d.text((PAD + 72, y + 240), f"{prate:.0f}%", font=_font(13, bold=True), fill=t["text"])
        d.text((W - PAD - 20, y + 242), f"常态 {tgt_p:.0f}%", font=_font(10), fill=t["dim"], anchor="ra")
        value_scale(d, scale_left, y + 256, scale_right - scale_left, prate, 0, 100,
                    p_cuts, p_words, p_segs, t, _font(10), tgt_p)

        y += 300 + 14

    # ---------- 一致性 ----------
    if has_cons:
        cnt = int(cons.get("count") or len(conflicts))
        color = t["bad"] if cnt else t["good"]
        y = _section(d, y, "记忆 ↔ 人设卡", t, f"检查 {cons.get('entries', 0)} 条记忆")
        _rr(d, (PAD, y, W - PAD, y + 34), 10, fill=t["card_alt"], outline=t["line"])
        d.ellipse((PAD + 14, y + 14, PAD + 20, y + 20), fill=color)
        d.text((PAD + 28, y + 9), f"冲突 {cnt} 处" if cnt else "没有发现矛盾",
               font=f_row, fill=color if cnt else t["text"])
        y += 42
        for c in conflicts[:3]:
            d.text((PAD + 28, y), str(c.get("topic", ""))[:18], font=f_small, fill=t["text"])
            d.text((PAD + 170, y), str(c.get("source", ""))[:24], font=f_small, fill=t["dim"])
            y += 26
        y += 4

    # ---------- 腔调 ----------
    habit_n = int(data.get("habit", 0))
    if dialects:
        y = _section(d, y, "腔调命中", t, f"角色习惯已忽略 {habit_n}" if habit_n else "")
        px = PAD
        for key in ["deepseek", "gemini", "claude", "gpt", "qwen", "glm", "doubao", "base"]:
            n = int(dialects.get(key, 0))
            if n <= 0:
                continue
            if key == "base":
                txt, color = f"通用 {n}", t["dim"]
            else:
                full, _, color = FAMILY_LABEL.get(key, (key, key, t["dim"]))
                txt = f"{full} 腔 {n}"
            tw3 = d.textlength(txt, font=f_small) + 22
            if px + tw3 > W - PAD:
                px = PAD
                y += 30
            _rr(d, (px, y, px + tw3, y + 24), 12, fill=t["card"], outline=t["line"])
            d.ellipse((px + 9, y + 9, px + 15, y + 15), fill=color)
            d.text((px + 19, y + 4), txt, font=f_small, fill=t["text"])
            px += tw3 + 8
        y += 38

    # ---------- 最近命中 ----------
    y = _section(d, y, "最近命中", t)
    if not hits:
        d.text((PAD + 4, y + 2), "今天没有命中", font=f_row, fill=t["dim"])
        y += 28
    for h in hits:
        is_ai = bool(h.get("ai"))
        color = t["warn"] if is_ai else t["bad"]
        _rr(d, (PAD, y, W - PAD, y + 26), 7, fill=t["card_alt"])
        d.rounded_rectangle((PAD, y, PAD + 3, y + 26), radius=2, fill=color)
        d.text((PAD + 14, y + 5), str(h.get("time", ""))[11:16], font=f_small, fill=t["dim"])
        chat_txt = str(h.get("chat_name") or "")
        no = str(h.get("chat_no") or "")
        kind = str(h.get("chat_kind") or "")
        label = f"{kind}·{chat_txt}" + (f"({no})" if no and no != chat_txt else "")
        d.text((PAD + 58, y + 5), label[:22], font=f_small, fill=t["dim"])
        txt = "「" + str(h.get("text", "")).replace("\n", " ")[:26] + "」"
        d.text((PAD + 208, y + 5), txt, font=f_small, fill=t["text"])
        _, short3, _ = FAMILY_LABEL.get(str(h.get("family") or ""), ("", "", t["dim"]))
        tag = ("人机味" if is_ai else "冲突") + (f"·{short3}" if short3 else "")
        d.text((W - PAD - 12, y + 5), tag, font=f_small, fill=color, anchor="ra")
        y += 30

    if cc_n:
        y += 4
        d.rounded_rectangle((PAD, y + 3, PAD + 3, y + 15), radius=2, fill=t["bad"])
        d.text((PAD + 12, y), "聊天事实冲突", font=_font(14, bold=True), fill=t["bad"])
        d.text((W - PAD, y + 1), f"{cc_n} 条", font=_font(12), fill=t["bad"], anchor="ra")
        y += 26
        for it in cc_items[:2]:
            d.text((PAD + 12, y), "· " + str(it.get("text", ""))[:38], font=_font(12), fill=t["text"])
            y += 20
            d.text((PAD + 18, y), str(it.get("reason", ""))[:52], font=_font(11), fill=t["dim"])
            y += 24

    if shadow_n:
        y += 4
        d.rounded_rectangle((PAD, y + 3, PAD + 3, y + 15), radius=2, fill=t["warn"])
        d.text((PAD + 12, y), "疑似漏检", font=_font(14, bold=True), fill=t["dim"])
        d.text((W - PAD, y + 1), f"{shadow_n} 条", font=_font(12), fill=t["dim"], anchor="ra")
        y += 26
        for it in shadow_items[:2]:
            d.text((PAD + 12, y), "· " + str(it.get("text", ""))[:40], font=_font(12), fill=t["dim"])
            d.text((W - PAD, y), str(it.get("chat_key", ""))[-14:], font=_font(12),
                   fill=t["dim"], anchor="ra")
            y += 26

    # ---------- 页脚 ----------
    y += 12
    d.line([(PAD, y), (W - PAD, y)], fill=t["line"], width=1)
    d.text((PAD, y + 14), "人设哨兵 · persona_guard", font=_font(11), fill=t["dim"])
    d.text((W - PAD, y + 14), "只统计，不干预", font=_font(11), fill=t["dim"], anchor="ra")

    img.save(out_path, format="PNG")
    return out_path
