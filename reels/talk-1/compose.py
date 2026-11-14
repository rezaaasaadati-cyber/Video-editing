"""Compose the talking-head reel (1080x1920, 30fps).

Inputs: work/prep_<c>.mp4 (graded, background-blurred, 2x upscaled), work/transcript_<c>.json (Whisper word
times), script.json (corrected text, one line per Whisper segment), assets/ (fonts, logo).

Layout (inspired by the framed-interview references): brand navy background with a fine grid, SAZAN logo on
top, the speaker in a rounded card, a thin progress line on the card, word-by-word captions in dark pills,
punch-in zooms on every new sentence, motion-graphic cutaways on the key numbers, and a CTA at the end.

Usage: python3 compose.py [--stills 0,90,...] [--out renders/talk-1-v1.mp4]
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
A = ROOT / "assets"
W, H, FPS = 1080, 1920, 30
PW, PH = 960, 1704                      # prepped footage size

NAVY = (14, 25, 43)
NAVY_D = (8, 14, 26)
CREAM = (244, 239, 230)
CYAN = (2, 190, 240)
ORANGE = (245, 140, 30)
RED = (232, 60, 50)
GREEN = (40, 200, 120)
WHITE = (255, 255, 255)

# card that holds the speaker
CX0, CY0, CW, CH = 50, 340, 980, 1200
RADIUS = 38
SRC_Y0 = 230                            # top of the crop inside the prepped frame
FACE = (480, 560)                       # zoom anchor (prepped coords)
SUB_Y = 1330


# ---------------- fonts ----------------
_F = {}


def fnt(weight, size):
    key = (weight, size)
    if key not in _F:
        _F[key] = ImageFont.truetype(str(A / "fonts" / f"IRANSansX-{weight}.ttf"), size)
    return _F[key]


FA = "۰۱۲۳۴۵۶۷۸۹"


def fa_num(n):
    return "".join(FA[int(ch)] for ch in str(n))


# ---------------- easing / layers ----------------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_back(t, k=1.7):
    t = clamp(t) - 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


def text_layer(s, f, fill, rtl=True):
    kw = {"direction": "rtl", "language": "fa"} if rtl else {}
    b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), s, font=f, **kw)
    layer = Image.new("RGBA", (b[2] - b[0] + 40, b[3] - b[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20 - b[0], 20 - b[1]), s, font=f, fill=fill, **kw)
    return layer


def place(img, layer, cx, cy, scale=1.0, alpha=1.0, blur=0.0, rot=0.0):
    if alpha <= 0:
        return
    if scale != 1.0:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.BICUBIC)
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, expand=True)
    if blur > 0.5:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    if alpha < 1:
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * clamp(alpha))))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def blur_in(img, layer, cx, cy, t_local, dur=0.22, scale=1.0):
    t = ease_out(t_local / dur)
    place(img, layer, cx, cy, scale * (1.1 - 0.1 * t), alpha=clamp(t_local / 0.08), blur=14 * (1 - t))


def pill(s, f, bg, fg, pad=(30, 14)):
    t = text_layer(s, f, fg)
    w, h = t.width - 40 + 2 * pad[0], t.height - 40 + 2 * pad[1]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=bg)
    out.alpha_composite(t, (pad[0] - 20, pad[1] - 20 + 2))
    return out


# ---------------- background, logo, card mask ----------------
def brand_bg():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    top, bot = np.array([18, 32, 56], np.float32), np.array([7, 12, 22], np.float32)
    base = top * (1 - y / H)[..., None] + bot * (y / H)[..., None]
    g = np.exp(-(((x - W / 2) / 600) ** 2 + ((y - 900) / 800) ** 2))
    base += g[..., None] * np.array(CYAN, np.float32) * 0.16
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)
    for gx in range(0, W, 90):
        d.line((gx, 0, gx, H), fill=(255, 255, 255, 12))
    for gy in range(0, H, 90):
        d.line((0, gy, W, gy), fill=(255, 255, 255, 12))
    grid = img
    return grid


def logo_for_dark():
    logo = Image.open(A / "sazan-logo.png").convert("RGBA")
    arr = np.array(logo).astype(int)
    sat = arr[:, :, :3].max(2) - arr[:, :, :3].min(2)
    grey = (sat < 40) & (arr[:, :, 3] > 0)
    arr[grey, 0], arr[grey, 1], arr[grey, 2] = CREAM
    out = Image.fromarray(arr.astype(np.uint8), "RGBA")
    return out.resize((360, int(out.height * 360 / out.width)), Image.LANCZOS)


BG = brand_bg()
LOGO = logo_for_dark()
CARD_MASK = Image.new("L", (CW, CH), 0)
ImageDraw.Draw(CARD_MASK).rounded_rectangle((0, 0, CW - 1, CH - 1), RADIUS, fill=255)
SHADOW = Image.new("RGBA", (CW + 160, CH + 160), (0, 0, 0, 0))
_sh = Image.new("RGBA", (CW, CH), (0, 0, 0, 170))
_sh.putalpha(CARD_MASK.point(lambda v: int(v * 0.7)))
SHADOW.alpha_composite(_sh, (80, 100))
SHADOW = SHADOW.filter(ImageFilter.GaussianBlur(36))


def static_frame():
    img = BG.copy()
    img.alpha_composite(SHADOW, (CX0 - 80, CY0 - 80))
    img.alpha_composite(LOGO, (W // 2 - LOGO.width // 2, 262 - LOGO.height // 2))
    return img


STATIC = static_frame()


# ---------------- edit decision list ----------------
SILENCES = {
    "a": [(3.658, 4.019), (13.047, 13.403), (27.057, 27.611), (35.377, 35.807)],
    "b": [(0.0, 0.463), (8.125, 8.562), (14.524, 15.019), (19.019, 19.457), (27.744, 28.490), (36.539, 36.982),
          (42.981, 43.399), (44.893, 45.385), (50.301, 50.746), (55.756, 56.667)],
}
ENDS = {"a": 40.15, "b": 59.45}


def build_edl():
    """Remove the middle of every pause longer than 0.3s (keep 0.10s either side)."""
    edl = []
    for c in "ab":
        t = 0.0
        for s, e in SILENCES[c]:
            if e - s > 0.3:
                if s + 0.10 > t:
                    edl.append((c, t, s + 0.10))
                t = max(t, e - 0.10)
        edl.append((c, t, ENDS[c]))
    out, acc = [], 0.0
    for c, a, b in edl:
        if b - a > 0.05:
            out.append({"clip": c, "in": a, "out": b, "at": acc})
            acc += b - a
    return out, acc


EDL, DURATION = build_edl()
TOTAL = int(round(DURATION * FPS))


def to_out(c, t):
    """Source time on clip c -> output time (None if cut)."""
    for seg in EDL:
        if seg["clip"] == c and seg["in"] <= t <= seg["out"] + 1e-6:
            return seg["at"] + t - seg["in"]
    # nearest following segment (word started in a trimmed pause)
    for seg in EDL:
        if seg["clip"] == c and seg["in"] > t:
            return seg["at"]
    return None


def seg_at(t_out):
    for k, seg in enumerate(EDL):
        if seg["at"] <= t_out < seg["at"] + seg["out"] - seg["in"]:
            return k, seg
    return len(EDL) - 1, EDL[-1]


# ---------------- captions ----------------
def build_words():
    script = json.load(open(ROOT / "script.json"))
    words = []
    for c in "ab":
        tr = json.load(open(ROOT / "work" / f"transcript_{c}.json"))
        for si, (seg, line) in enumerate(zip(tr, script[c])):
            ww = seg["words"]
            toks = line.split()
            for k, tok in enumerate(toks):
                # proportional mapping of corrected tokens onto Whisper word times
                j0 = int(k * len(ww) / len(toks))
                j1 = max(j0, int((k + 1) * len(ww) / len(toks)) - 1)
                s, e = ww[j0]["s"], ww[min(j1, len(ww) - 1)]["e"]
                os_, oe = to_out(c, s), to_out(c, e)
                if os_ is None:
                    continue
                words.append({"w": tok, "s": os_, "e": max(oe or os_, os_ + 0.08), "clip": c, "seg": si,
                              "brk": tok.endswith(("،", ":", "؟", ".", ","))})
    return words


WORDS = build_words()


def build_chunks(words, maxw=3):
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= maxw or cur[-1]["seg"] != w["seg"] or cur[-1]["clip"] != w["clip"]):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w["brk"]:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out = []
    for k, ch in enumerate(chunks):
        end = chunks[k + 1][0]["s"] if k + 1 < len(chunks) else ch[-1]["e"] + 0.3
        out.append({"words": ch, "s": ch[0]["s"], "e": min(end, ch[-1]["e"] + 0.6)})
    return out


CHUNKS = build_chunks(WORDS)
SUB_F = fnt("Heavy", 60)


def caption_layer(chunk, t):
    """Dark pill with the chunk; the word being spoken is cyan."""
    f = SUB_F
    space = int(f.getlength(" "))
    parts = []
    for w in chunk["words"]:
        active = w["s"] <= t < (w["e"] + 0.05)
        parts.append(text_layer(w["w"], f, CYAN if active else WHITE))
    inner_w = sum(p.width - 40 for p in parts) + space * (len(parts) - 1)
    hgt = max(p.height for p in parts) - 40
    padx, pady = 34, 16
    out = Image.new("RGBA", (inner_w + 2 * padx, hgt + 2 * pady), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, out.width - 1, out.height - 1), 24, fill=NAVY_D + (215,))
    x = out.width - padx
    for p in parts:                        # right to left
        x -= p.width - 40
        out.alpha_composite(p, (x - 20, pady - 20 + 4))
        x -= space
    return out


# ---------------- moments (cutaways and overlays), source times ----------------
def word_time(c, seg, token):
    for w in WORDS:
        if w["clip"] == c and w["seg"] == seg and token in w["w"]:
            return w["s"]
    raise KeyError(token)


def span(c, s, e):
    return to_out(c, s), to_out(c, e)


MOMENTS = [
    ("hook", *span("a", 0.0, 3.6)),
    ("name", *span("a", 7.55, 12.9)),
    ("home", *span("a", 18.1, 21.8)),
    ("decade", *span("a", 32.75, 36.2)),
    ("count", *span("b", 0.5, 4.1)),
    ("no", *span("b", 8.6, 14.45)),
    ("yes", *span("b", 15.05, 19.0)),
    ("keyword", word_time("b", 7, "جسارت"), word_time("b", 7, "جسارت") + 2.6),
    ("question", *span("b", 45.4, 50.25)),
    ("cta", *span("b", 56.7, 59.4)),
]
CUTAWAYS = {"home", "decade", "count", "no", "yes"}
HIDE_SUBS = {"hook", "question", "cta", "count", "no", "yes", "decade"}


def active_moment(t):
    for name, s, e in MOMENTS:
        if s <= t < e:
            return name, t - s, e - s
    return None, 0, 0


# ---------------- graphics for the cutaways ----------------
def card_canvas(colour=NAVY):
    c = Image.new("RGBA", (CW, CH), colour + (255,))
    d = ImageDraw.Draw(c)
    for gx in range(0, CW, 70):
        d.line((gx, 0, gx, CH), fill=(255, 255, 255, 14))
    for gy in range(0, CH, 70):
        d.line((0, gy, CW, gy), fill=(255, 255, 255, 14))
    return c


def icon_house(size, colour):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    w = max(6, s // 18)
    d.line([(s * .12, s * .5), (s * .5, s * .15), (s * .88, s * .5)], fill=colour, width=w, joint="curve")
    d.rectangle((s * .22, s * .48, s * .78, s * .88), outline=colour, width=w)
    d.rectangle((s * .43, s * .64, s * .57, s * .88), fill=colour)
    return im


def icon_cup(size, colour, steam=0.0):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    w = max(6, s // 18)
    d.rounded_rectangle((s * .18, s * .42, s * .7, s * .86), radius=s // 10, outline=colour, width=w)
    d.arc((s * .58, s * .5, s * .86, s * .74), -90, 90, fill=colour, width=w)
    d.line((s * .12, s * .92, s * .78, s * .92), fill=colour, width=w)
    for k in range(3):
        x = s * (.3 + k * .14)
        off = math.sin(steam * 6 + k) * s * .02
        d.arc((x - s * .05 + off, s * .12, x + s * .05 + off, s * .36), 100, 260, fill=colour + (200,), width=w // 2)
    return im


def icon_store(size, colour):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    w = max(6, s // 18)
    d.rectangle((s * .14, s * .4, s * .86, s * .88), outline=colour, width=w)
    for k in range(4):
        x0 = s * (.1 + k * .2)
        d.pieslice((x0, s * .18, x0 + s * .2, s * .46), 0, 180, fill=colour)
    d.rectangle((s * .1, s * .2, s * .9, s * .32), fill=colour)
    d.rectangle((s * .42, s * .6, s * .58, s * .88), fill=colour)
    return im


def gfx_home(t, dur):
    c = card_canvas()
    place(c, icon_house(380, CREAM), CW / 2, 420, ease_back(t / 0.35), alpha=clamp(t / 0.1))
    if t > 0.35:
        place(c, icon_cup(190, ORANGE, t), CW / 2, 470, ease_back((t - 0.35) / 0.3), alpha=1)
    blur_in(c, text_layer("قهوه = خونه", fnt("Heavy", 110), CREAM), CW / 2, 770, t - 0.5)
    blur_in(c, text_layer("دستگاه اسپرسو و پاد، توی آشپزخونهٔ خودمون", fnt("Medium", 42), (200, 210, 225)),
            CW / 2, 880, t - 0.8)
    return c


def gfx_decade(t, dur):
    c = card_canvas()
    blur_in(c, text_layer("دههٔ ۸۰ میلادی", fnt("Heavy", 96), ORANGE), CW / 2, 250, t)
    hx, sx, y = CW * .74, CW * .26, 560
    place(c, icon_house(260, CREAM), hx, y, ease_back(t / .3))
    if t > .45:
        p = ease_out((t - .45) / .5)
        d = ImageDraw.Draw(c)
        x1 = hx - 150 - (hx - sx - 300) * p
        d.line((hx - 150, y, x1, y), fill=CYAN, width=12)
        if p > .95:
            d.polygon([(x1 - 4, y), (x1 + 34, y - 26), (x1 + 34, y + 26)], fill=CYAN)
    if t > .9:
        place(c, icon_store(260, CYAN), sx, y, ease_back((t - .9) / .3))
    blur_in(c, text_layer("مردم رو از خونه بیاریم توی کافه", fnt("Heavy", 62), CREAM), CW / 2, 820, t - 1.2)
    return c


DOT_COLS, DOT_ROWS, DOT = 14, 18, 40          # 252 cells, 242 used


def dots_grid(n_red, n_green, appear=1.0):
    c = card_canvas()
    d = ImageDraw.Draw(c)
    gw = DOT_COLS * DOT
    x0, y0 = (CW - gw) / 2 + DOT / 2, 330
    shown = int(242 * appear)
    for k in range(242):
        if k >= shown:
            break
        r, q = divmod(k, DOT_COLS)
        x = x0 + (DOT_COLS - 1 - q) * DOT          # fill right-to-left
        y = y0 + r * DOT
        col = (90, 105, 130)
        if k < n_red:
            col = RED
        elif k >= 242 - n_green:
            col = GREEN
        d.ellipse((x - 14, y - 14, x + 14, y + 14), fill=col)
    return c


def gfx_count(t, dur):
    n = int(242 * ease_out(t / 1.6))
    c = dots_grid(0, 0, n / 242)
    blur_in(c, text_layer(fa_num(n), fnt("ExtraBlack", 180), CREAM), CW / 2, 150, t)
    place(c, pill("سرمایه‌گذار", fnt("Heavy", 46), CYAN, NAVY_D), CW / 2, 1100, alpha=clamp((t - .3) / .2))
    return c


def gfx_no(t, dur):
    n = int(217 * ease_in_out(t / 3.2))
    c = dots_grid(n, 0)
    place(c, text_layer(fa_num(n), fnt("ExtraBlack", 180), RED), CW / 2 + 90, 150)
    place(c, text_layer("«نه»", fnt("ExtraBlack", 110), CREAM), CW / 2 - 200, 160)
    # stamp "NO" pops on each spoken "نه" near the end
    if t > dur - 1.6:
        k = int((t - (dur - 1.6)) / 0.4)
        place(c, pill("نه!", fnt("ExtraBlack", 80), RED, WHITE), CW / 2, 1100, ease_back(((t - (dur - 1.6)) % .4) / .15),
              rot=(-6 if k % 2 else 6))
    return c


def gfx_yes(t, dur):
    c = dots_grid(217, int(25 * ease_out(t / .8)))
    place(c, text_layer(fa_num(int(25 * ease_out(t / .8))), fnt("ExtraBlack", 180), GREEN), CW / 2 + 90, 150)
    place(c, text_layer("«بله»", fnt("ExtraBlack", 110), CREAM), CW / 2 - 200, 160)
    place(c, pill("بیا تستش کنیم", fnt("Heavy", 50), GREEN, NAVY_D), CW / 2, 1100, alpha=clamp((t - 1.6) / .2))
    return c


GFX = {"home": gfx_home, "decade": gfx_decade, "count": gfx_count, "no": gfx_no, "yes": gfx_yes}


# ---------------- overlays on top of the speaker ----------------
def ov_hook(img, t, dur):
    # big kinetic hook over the lower half of the card
    place(img, text_layer("۲۱۷ نفر", fnt("ExtraBlack", 200), CREAM), W / 2, 1110, 1.08 - .08 * ease_back(t / .25))
    p = pill("بهش گفتن «نه»", fnt("ExtraBlack", 76), RED, WHITE)
    if t > .5:
        place(img, p, W / 2, 1290, ease_back((t - .5) / .25), rot=-3)
    if t > 1.7:
        blur_in(img, pill("اما الان یه اسطوره‌ست", fnt("Heavy", 56), CYAN, NAVY_D), W / 2, 1420, t - 1.7)


def ov_name(img, t, dur):
    x = W - 90 - 300 * (1 - ease_out(t / .35))
    a = clamp(t / .15) * (1 - clamp((t - dur + .3) / .3))
    name = pill("هاوارد شولتز", fnt("Heavy", 58), CREAM, NAVY_D)
    sub = pill("استارباکس", fnt("Bold", 42), (0, 112, 74), WHITE)
    place(img, name, x - name.width / 2, 1080, alpha=a)
    place(img, sub, x - sub.width / 2 - 10, 1170, alpha=a * clamp((t - .2) / .2))


def ov_keyword(img, t, dur):
    a = 1 - clamp((t - dur + .25) / .25)
    blur_in(img, text_layer("جسارتِ", fnt("Heavy", 80), CREAM), W / 2, 1010, t)
    place(img, pill("«نه» شنیدن", fnt("ExtraBlack", 110), ORANGE, NAVY_D), W / 2, 1150,
          ease_back((t - .2) / .3), alpha=a * clamp((t - .2) / .1), rot=-2)


def ov_question(img, t, dur):
    box = Image.new("RGBA", (880, 330), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, 879, 329), 36, fill=CREAM + (245,))
    l1 = text_layer("امروز چند تا", fnt("Heavy", 70), NAVY)
    box.alpha_composite(l1, (440 - l1.width // 2, 30))
    q = text_layer("«نه» شنیدی؟", fnt("ExtraBlack", 120), RED)
    box.alpha_composite(q, (440 - q.width // 2, 130))
    s = ease_back(t / .35)
    place(img, box, W / 2, 1180, s, rot=2 * (1 - s))


def ov_cta(img, t, dur):
    box = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, 899, 299), 36, fill=CYAN + (250,))
    l1 = text_layer("بفرستش برای کسی که", fnt("Heavy", 60), NAVY_D)
    l2 = text_layer("از «نه» شنیدن می‌ترسه", fnt("ExtraBlack", 78), NAVY_D)
    box.alpha_composite(l1, (450 - l1.width // 2, 40))
    box.alpha_composite(l2, (450 - l2.width // 2, 140))
    place(img, box, W / 2, 1210, ease_back(t / .35))
    # paper plane flies off
    pp = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(pp).polygon([(10, 60), (110, 15), (75, 105), (55, 70)], fill=WHITE)
    fly = ease_in_out((t - .6) / 1.2)
    place(img, pp, 150 + 120 * fly, 1040 - 220 * fly, 1.0, alpha=clamp((t - .4) / .2) * (1 - clamp((t - 1.6) / .3)),
          rot=20 * fly)


OVERLAYS = {"hook": ov_hook, "name": ov_name, "keyword": ov_keyword, "question": ov_question, "cta": ov_cta}


# ---------------- zoom per sentence ----------------
def zoom_for(t_out):
    """New sentence -> new framing; alternate wide / medium / tight with a 4-frame ease."""
    levels = [1.0, 1.18, 1.0, 1.32]
    idx, prev_idx, since = 0, 0, 99.0
    sent = 0
    for w in WORDS:
        if w["s"] > t_out:
            break
        key = (w["clip"], w["seg"])
        if sent == 0 or key != last:
            prev_idx, idx = idx, sent % len(levels)
            since = t_out - w["s"]
            sent += 1
        last = key
    target, prev = levels[idx], levels[prev_idx]
    z = prev + (target - prev) * ease_out(since / 0.13)
    return z + 0.03 * clamp(since / 4)          # slow push inside each sentence


# ---------------- footage reader ----------------
class Reader:
    def __init__(self):
        self.proc, self.key, self.pos = None, None, 0

    def frame(self, seg_k, seg, t_in):
        n = int(round((t_in - seg["in"]) * FPS))
        if self.key != seg_k or n < self.pos:
            if self.proc:
                self.proc.kill()
            self.proc = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-ss", f"{seg['in']:.3f}", "-i", str(ROOT / "work" / f"prep_{seg['clip']}.mp4"),
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
            self.key, self.pos, self.last = seg_k, 0, None
        while self.pos <= n:
            b = self.proc.stdout.read(PW * PH * 3)
            if len(b) < PW * PH * 3:
                break
            self.last = b
            self.pos += 1
        return Image.frombytes("RGB", (PW, PH), self.last)


READER = Reader()


def speaker_card(fr, z, grey=0.0):
    scale = CW / PW * z
    cw, ch = CW / scale, CH / scale
    fx, fy = FACE
    x0 = clamp(fx - cw / 2, 0, PW - cw)
    y0 = clamp(SRC_Y0 + (fy - SRC_Y0) * (1 - 1 / z) , 0, PH - ch)
    crop = fr.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((CW, CH), Image.BICUBIC)
    if grey > 0:
        g = crop.convert("L").convert("RGB")
        crop = Image.blend(crop, g, grey)
    return crop.convert("RGBA")


def render(n):
    t = n / FPS
    k, seg = seg_at(t)
    t_in = seg["in"] + (t - seg["at"])
    img = STATIC.copy()
    name, tl, dur = active_moment(t)

    if name in CUTAWAYS:
        card = GFX[name](tl, dur)
        # quick wipe in / out so the cutaway feels deliberate
        inn, out = ease_out(tl / .18), ease_out((dur - tl) / .18)
        if inn < 1 or out < 1:
            fr = READER.frame(k, seg, t_in)
            base = speaker_card(fr, zoom_for(t))
            m = Image.new("L", (CW, CH), 0)
            w = int(CW * min(inn, out))
            ImageDraw.Draw(m).rectangle((CW - w, 0, CW, CH), fill=255)
            base.paste(card, (0, 0), m)
            card = base
    else:
        fr = READER.frame(k, seg, t_in)
        grey = 1 - clamp((t - 0.9) / 0.3) if t < 1.2 else 0.0      # hook opens in black & white
        card = speaker_card(fr, zoom_for(t), grey)
    img.paste(card, (CX0, CY0), CARD_MASK)

    # progress line on top of the card
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((CX0 + 40, CY0 - 22, CX0 + CW - 40, CY0 - 16), 3, fill=(255, 255, 255, 40))
    px = CX0 + CW - 40 - (CW - 80) * (t / DURATION)
    d.rounded_rectangle((px, CY0 - 22, CX0 + CW - 40, CY0 - 16), 3, fill=ORANGE)

    if name in OVERLAYS:
        OVERLAYS[name](img, tl, dur)
    if name not in HIDE_SUBS:
        for ch in CHUNKS:
            if ch["s"] <= t < ch["e"]:
                cap = caption_layer(ch, t)
                pop = ease_back(min(1, (t - ch["s"]) / 0.12), 1.4)
                place(img, cap, W / 2, SUB_Y, 0.9 + 0.1 * pop)
                break
    return img.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills")
    ap.add_argument("--out", default=str(ROOT / "renders" / "talk-1-v1.mp4"))
    ap.add_argument("--audio", default=str(ROOT / "work" / "voice.wav"))
    a = ap.parse_args()
    if a.stills:
        for n in map(int, a.stills.split(",")):
            render(n).save(ROOT / "work" / f"still_{n:04d}.png")
        return
    Path(a.out).parent.mkdir(exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", a.audio, "-map", "0:v", "-map", "1:a", "-shortest",
                          "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                          "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", a.out], stdin=subprocess.PIPE)
    for n in range(TOTAL):
        p.stdin.write(render(n).tobytes())
        if n % 300 == 0:
            print(f"{n}/{TOTAL}", flush=True)
    p.stdin.close()
    p.wait()
    print("wrote", a.out, f"{DURATION:.2f}s")


if __name__ == "__main__":
    main()
