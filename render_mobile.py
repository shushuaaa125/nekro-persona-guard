"""人设哨兵 - 手机版卡片（440 宽，四条刻度）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import ImageDraw

from .render import (
    FAMILY_LABEL,
    THEMES,
    _avatar,
    _bg,
    _circle,
    _font,
    _ring,
    _rr,
    _title_font,
    dialogue_band,
    dialogue_scale,
    human_band,
    human_scale,
    value_scale,
)

MW = 440
MPAD = 22


def render_mobile_card(
    data: Dict[str, Any],
    out_path: Path,
    theme: str = "dark",
    avatar_url: str = "",
    avatar_path: Optional[Path] = None,
    title_font: str = "kuaile",
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

    H = 190
    H += 2 * 84 + 12          # 统计 2x2
    H += 26 + max(1, len(chats)) * 56
    if models:
        H += 26 + len(models) * 48
    if has_match:
        H += 26 + 342
    if has_cons:
        H += 26 + 40
    if dialects:
        H += 26 + 34
    H += 26 + (len(hits) * 42 if hits else 26)
    if shadow_n:
        H += 26 + min(2, len(shadow_items)) * 22
    if cc_n:
        H += 26 + min(2, len(cc_items)) * 40
    H += 44

    img = _bg(MW, H, t)
    d = ImageDraw.Draw(img)

    f_title = _title_font(23, title_font)
    f_sub = _font(11)
    f_big = _font(24, bold=True)
    f_small = _font(11)
    f_row = _font(13)

    y = 26
    av_size = 44
    av = _avatar(avatar_url, avatar_path)
    if av is not None:
        circ = _circle(av, av_size)
        img.paste(circ, (MPAD, y), circ)
        d.ellipse((MPAD - 1, y - 1, MPAD + av_size, y + av_size), outline=t["accent"], width=2)
    else:
        d.ellipse((MPAD, y, MPAD + av_size, y + av_size), fill=t["card"], outline=t["accent"], width=2)

    tx = MPAD + av_size + 12
    d.text((tx, y + 2), "人设哨兵", font=f_title, fill=t["text"])
    box = d.textbbox((tx, y + 2), "人设哨兵", font=f_title)
    d.text((tx, box[3] + 3), str(data.get("date", "")), font=f_small, fill=t["dim"])
    d.text((MW - MPAD, y + 4), "日报", font=f_sub, fill=t["dim"], anchor="ra")

    model_name = str(data.get("model") or "")
    pill_txt = model_name if model_name and model_name != "unknown" else "模型未知"
    pw = d.textlength(pill_txt, font=f_small) + 22
    _rr(d, (MPAD, y + av_size + 10, MPAD + pw, y + av_size + 32), 11, fill=t["card"], outline=t["line"])
    d.ellipse((MPAD + 9, y + av_size + 18, MPAD + 14, y + av_size + 23), fill=t["accent"])
    d.text((MPAD + 19, y + av_size + 13), pill_txt, font=f_small, fill=t["text"])
    y += av_size + 44

    # 2x2 统计
    stats = [
        ("消息", str(data.get("total", 0)), t["text"]),
        ("人机味", str(data.get("ai", 0)), t["warn"]),
        ("设定冲突", str(data.get("conflict", 0)), t["bad"]),
        ("称呼开头", f"{data.get('address', 0)}/{data.get('total', 0)}", t["accent"]),
    ]
    gap = 10
    bw = (MW - MPAD * 2 - gap) // 2
    for i, (k, v, color) in enumerate(stats):
        col, row = i % 2, i // 2
        x0 = MPAD + col * (bw + gap)
        y0 = y + row * (84 + 12)
        _rr(d, (x0, y0, x0 + bw, y0 + 84), 12, fill=t["card"], outline=t["line"])
        d.text((x0 + 12, y0 + 12), k, font=f_small, fill=t["dim"])
        d.text((x0 + 12, y0 + 34), v, font=f_big, fill=color)
    y += 2 * 84 + 12 + 18

    def sec(title: str, right: str = "") -> None:
        nonlocal y
        d.rounded_rectangle((MPAD, y + 2, MPAD + 3, y + 14), radius=2, fill=t["accent"])
        d.text((MPAD + 10, y), title, font=_font(12, bold=True), fill=t["dim"])
        if right:
            d.text((MW - MPAD, y + 1), right, font=f_small, fill=t["dim"], anchor="ra")
        y += 26

    # 按会话
    sec("按会话统计", f"{len(chats)} 个")
    if not chats:
        d.text((MPAD + 2, y), "今天还没有记录", font=f_row, fill=t["dim"])
        y += 40
    for c in chats:
        total = int(c.get("total", 0)) or 0
        rate = f"{round(100 * int(c.get('address', 0)) / total)}%" if total else "—"
        _rr(d, (MPAD, y, MW - MPAD, y + 50), 10, fill=t["card_alt"], outline=t["line"])
        name = str(c.get("name", ""))[:16]
        d.text((MPAD + 12, y + 7), name, font=f_row, fill=t["text"])
        tag, _, tcolor = FAMILY_LABEL.get(str(c.get("family") or ""), ("", "", t["dim"]))
        if tag:
            nw = d.textlength(name, font=f_row)
            tw = d.textlength(tag, font=f_small) + 12
            _rr(d, (MPAD + 16 + nw, y + 8, MPAD + 16 + nw + tw, y + 22), 7, fill=t["card"], outline=t["line"])
            d.text((MPAD + 22 + nw, y + 9), tag, font=f_small, fill=tcolor)
        d.text((MW - MPAD - 12, y + 7), f"{total} 条", font=f_small, fill=t["dim"], anchor="ra")
        ai_n, cf_n = int(c.get("ai", 0)), int(c.get("conflict", 0))
        d.text((MPAD + 12, y + 29), f"人机味 {ai_n} · 冲突 {cf_n} · 称呼 {rate}",
               font=f_small, fill=t["warn"] if ai_n else t["dim"])
        y += 56

    # 按模型
    if models:
        sec("按模型统计")
        for m in models:
            fam2 = str(m.get("family") or "")
            full, _, color = FAMILY_LABEL.get(fam2, (fam2, fam2, t["dim"]))
            total = int(m.get("total", 0)) or 0
            rate = f"{round(100 * int(m.get('address', 0)) / total)}%" if total else "—"
            _rr(d, (MPAD, y, MW - MPAD, y + 42), 9, fill=t["card_alt"], outline=t["line"])
            d.ellipse((MPAD + 10, y + 12, MPAD + 16, y + 18), fill=color)
            d.text((MPAD + 22, y + 6), full, font=f_row, fill=t["text"])
            d.text((MW - MPAD - 12, y + 6), f"{total} 条", font=f_small, fill=t["dim"], anchor="ra")
            d.text((MPAD + 22, y + 24),
                   f"人机味 {int(m.get('ai', 0))} · 冲突 {int(m.get('conflict', 0))} · 称呼 {rate}",
                   font=f_small, fill=t["dim"])
            y += 48
        y += 4

    # 匹配度：圆环 + 四条刻度
    if has_match:
        sec("人设匹配度")
        score = float(match.get("score") or 0)
        color = t["good"] if score >= 75 else (t["warn"] if score >= 55 else t["bad"])
        _rr(d, (MPAD, y, MW - MPAD, y + 342), 12, fill=t["card"], outline=t["line"])

        cx, cy = MPAD + 56, y + 52
        _ring(d, cx, cy, 30, score, color, t["track"])
        d.text((cx, cy - 12), f"{score:.0f}", font=_font(19, bold=True), fill=color, anchor="ma")
        d.text((cx, cy + 11), "/100", font=_font(9), fill=t["dim"], anchor="ma")

        parts = dict(match.get("parts") or {})
        setting_val = float(parts.get("设定一致") or 100)
        sc = t["good"] if setting_val >= 75 else (t["warn"] if setting_val >= 55 else t["bad"])
        d.text((MPAD + 112, y + 26), "设定一致", font=_font(10), fill=t["dim"])
        d.text((MPAD + 112, y + 42), f"{setting_val:.0f}", font=_font(18, bold=True), fill=sc)

        dialogue_val = float(parts.get("对话感") or 50)
        human_val = float(parts.get("去人机味") or 50)
        avg_len = float(match.get("avg_len") or 26)
        tgt_len = float(match.get("target_len") or 26)
        prate = float(match.get("particle_rate") or 50)
        tgt_p = float(match.get("target_particle") or 50)

        sx = MPAD + 16
        sw = MW - MPAD * 2 - 36

        d.text((sx, y + 96), "对话感", font=_font(10), fill=t["dim"])
        d.text((sx + 44, y + 92), dialogue_band(dialogue_val), font=_font(12, bold=True), fill=t["text"])
        dialogue_scale(d, sx, y + 120, sw, dialogue_val, t, _font(9))

        d.text((sx, y + 158), "活人感", font=_font(10), fill=t["dim"])
        d.text((sx + 44, y + 154), human_band(human_val), font=_font(12, bold=True), fill=t["text"])
        human_scale(d, sx, y + 182, sw, human_val, t, _font(9))

        len_cuts = [tgt_len * 0.7, tgt_len * 0.9, tgt_len * 1.2]
        len_segs = [(0.55, 0.62, 0.72), (0.48, 0.66, 0.78), (0.80, 0.72, 0.50), (0.88, 0.60, 0.42)]
        d.text((sx, y + 220), "句长", font=_font(10), fill=t["dim"])
        d.text((sx + 34, y + 216), f"{avg_len:.0f} 字", font=_font(12, bold=True), fill=t["text"])
        d.text((MW - MPAD - 20, y + 218), f"常态 {tgt_len:.0f}", font=_font(9), fill=t["dim"], anchor="ra")
        value_scale(d, sx, y + 244, sw, avg_len, 8, 60, len_cuts,
                    ["太短", "偏短", "偏长", "太长"], len_segs, t, _font(9), tgt_len)

        p_cuts = [tgt_p * 0.6, tgt_p * 0.9, tgt_p * 1.3]
        p_segs = [(0.50, 0.60, 0.70), (0.55, 0.68, 0.78), (0.85, 0.72, 0.48), (0.90, 0.58, 0.42)]
        d.text((sx, y + 282), "语气词", font=_font(10), fill=t["dim"])
        d.text((sx + 44, y + 278), f"{prate:.0f}%", font=_font(12, bold=True), fill=t["text"])
        d.text((MW - MPAD - 20, y + 280), f"常态 {tgt_p:.0f}%", font=_font(9), fill=t["dim"], anchor="ra")
        value_scale(d, sx, y + 306, sw, prate, 0, 100, p_cuts,
                    ["太素", "偏素", "偏满", "太满"], p_segs, t, _font(9), tgt_p)

        y += 342 + 14

    # 一致性
    if has_cons:
        cnt = int(cons.get("count") or len(conflicts))
        color = t["bad"] if cnt else t["good"]
        sec("记忆 ↔ 人设卡")
        _rr(d, (MPAD, y, MW - MPAD, y + 32), 9, fill=t["card_alt"], outline=t["line"])
        d.ellipse((MPAD + 12, y + 13, MPAD + 18, y + 19), fill=color)
        d.text((MPAD + 26, y + 8), f"冲突 {cnt} 处" if cnt else "没有发现矛盾",
               font=f_row, fill=color if cnt else t["text"])
        y += 40

    # 腔调
    if dialects:
        sec("腔调命中", f"习惯忽略 {int(data.get('habit', 0))}" if int(data.get("habit", 0)) else "")
        px = MPAD
        for key in ["deepseek", "gemini", "claude", "gpt", "qwen", "glm", "doubao", "base"]:
            n = int(dialects.get(key, 0))
            if n <= 0:
                continue
            if key == "base":
                txt, color = f"通用 {n}", t["dim"]
            else:
                full, _, color = FAMILY_LABEL.get(key, (key, key, t["dim"]))
                txt = f"{full} {n}"
            tw3 = d.textlength(txt, font=f_small) + 20
            if px + tw3 > MW - MPAD:
                px = MPAD
                y += 28
            _rr(d, (px, y, px + tw3, y + 22), 11, fill=t["card"], outline=t["line"])
            d.ellipse((px + 8, y + 8, px + 13, y + 13), fill=color)
            d.text((px + 17, y + 3), txt, font=f_small, fill=t["text"])
            px += tw3 + 6
        y += 34

    # 最近命中
    sec("最近命中")
    if not hits:
        d.text((MPAD + 2, y), "今天没有命中", font=f_row, fill=t["dim"])
        y += 26
    for h in hits:
        is_ai = bool(h.get("ai"))
        color = t["warn"] if is_ai else t["bad"]
        _rr(d, (MPAD, y, MW - MPAD, y + 36), 8, fill=t["card_alt"])
        d.rounded_rectangle((MPAD, y, MPAD + 3, y + 36), radius=2, fill=color)
        d.text((MPAD + 12, y + 4), str(h.get("time", ""))[11:16], font=f_small, fill=t["dim"])
        chat_txt = str(h.get("chat_name") or "")
        no = str(h.get("chat_no") or "")
        kind = str(h.get("chat_kind") or "")
        label = f"{chat_txt}({no})" if no and no != chat_txt else chat_txt
        if len(label) > 15:
            label = label[:14] + "…"
        d.text((MPAD + 50, y + 4), f"{kind}·{label}" if kind else label, font=f_small, fill=t["dim"])
        d.text((MW - MPAD - 10, y + 4), "人机味" if is_ai else "冲突", font=f_small, fill=color, anchor="ra")
        d.text((MPAD + 52, y + 17), "「" + str(h.get("text", ""))[:24] + "」", font=f_small, fill=t["text"])
        y += 42

    # 聊天事实冲突
    if cc_n:
        sec("聊天事实冲突", f"{cc_n} 条")
        for it in cc_items[:2]:
            d.text((MPAD + 2, y), "· " + str(it.get("text", ""))[:24],
                   font=f_small, fill=t["bad"])
            y += 18
            d.text((MPAD + 12, y), str(it.get("reason", ""))[:32],
                   font=f_small, fill=t["dim"])
            y += 22

    # 疑似漏检
    if shadow_n:
        sec("疑似漏检", f"{shadow_n} 条")
        for it in shadow_items[:2]:
            d.text((MPAD + 2, y), "· " + str(it.get("text", ""))[:26], font=f_small, fill=t["dim"])
            d.text((MW - MPAD - 2, y), str(it.get("chat_key", ""))[-10:], font=f_small,
                   fill=t["dim"], anchor="ra")
            y += 22

    y += 10
    d.line([(MPAD, y), (MW - MPAD, y)], fill=t["line"], width=1)
    d.text((MPAD, y + 12), "人设哨兵 · persona_guard", font=_font(10), fill=t["dim"])
    d.text((MW - MPAD, y + 12), "只统计，不干预", font=_font(10), fill=t["dim"], anchor="ra")

    img.save(out_path, format="PNG")
    return out_path
