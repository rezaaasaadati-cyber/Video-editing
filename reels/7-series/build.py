"""Render the "MBA nakhoon / 7 series" reel (1080x1920, 30fps), v8. Audio from music.py.

v7: graphic dark backgrounds (grid, glow, outlined marquee titles, progress bar), new hook
"این ۷ سریال رو ببینی / دیگه / دانشگاه / نیاز نداری." with poster flash-cuts behind it.

v3 look: kinetic typography on alternating flat navy / cream backgrounds, SAZAN brand
colours, blur-in words, a rolling counter, a "save" button that gets tapped, logo outro.

Frames are drawn with Pillow (raqm for Persian shaping) and piped into ffmpeg.
Usage: python3 build.py [--safe] [--out renders/7-series-v3.mp4] [--stills 0,10,60]

One font throughout: Estedad (OFL), in Black / ExtraBold / Bold weights.
"""
import argparse
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
A = ROOT / "assets"
W, H, FPS = 1080, 1920, 30
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 220, 1470, 35

# SAZAN palette (sampled from the logo) + editorial neutrals
NAVY = (14, 25, 43)
CREAM = (244, 239, 230)
CYAN = (2, 190, 240)
TEAL = (10, 120, 160)
ORANGE = (245, 140, 30)
YELLOW = (255, 196, 40)
WHITE = (255, 255, 255)

SERIES = [
    ("p1.jpg", "SUITS", "کت‌وشلواری‌ها", "مذاکره از موضع قدرت"),
    ("p2.jpg", "SUCCESSION", "جانشینی", "بازی قدرت در شرکت"),
    ("p3.jpg", "BILLIONS", "میلیاردها", "روانشناسی رقابت"),
    ("p4.jpg", "MAD MEN", "مردان دیوانه", "فروش و تبلیغات"),
    ("p5.jpg", "SILICON VALLEY", "دره سیلیکون", "ساختن استارتاپ از صفر"),
    ("p6.jpg", "SUPER PUMPED", "داستان اوبر", "رشد سریع و هزینه‌اش"),
    ("p7.jpg", "THE DROPOUT", "ترک تحصیل", "دروغ در بیزنس چه می‌کند"),
]
HANDLE = "@shanehsazanzadeh.abbas"
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

BEAT = 12              # hook word length in frames (0.4s)
HOOK_F = BEAT * 4      # 1.6s
EACH_F = 48            # 1.6s per series = one bar at 150 BPM
SAVE_F = 48            # 1.6s grid + save tap (tap on beat 4)
OUTRO_F = 60           # 2.0s logo
TOTAL = HOOK_F + EACH_F * len(SERIES) + SAVE_F + OUTRO_F

# ---------- fonts ----------
_FONTS = {}


def font(name, size, var=None):
    key = (name, size, var)
    if key not in _FONTS:
        f = ImageFont.truetype(str(A / "fonts" / name), size)
        if var:
            f.set_variation_by_name(var)
        _FONTS[key] = f
    return _FONTS[key]


def rubik(size, w="Black"):
    """One font throughout: Estedad (OFL). Name kept so call sites stay unchanged."""
    weight = {"Black": "Black", "ExtraBold": "ExtraBold", "Bold": "Bold", "Medium": "Bold"}[w]
    return font(f"Estedad-{weight}.ttf", size)


# ---------- easing ----------
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


# ---------- layers ----------
def kw(rtl):
    return {"direction": "rtl", "language": "fa"} if rtl else {}


def text_layer(s, f, fill, rtl=True):
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    b = tmp.textbbox((0, 0), s, font=f, **kw(rtl))
    pad = 40
    layer = Image.new("RGBA", (b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad - b[0], pad - b[1]), s, font=f, fill=fill, **kw(rtl))
    return layer


def pill_layer(s, f, bg, fg, pad=(34, 16), radius=None):
    t = text_layer(s, f, fg)
    w, h = t.width - 80 + 2 * pad[0], t.height - 80 + 2 * pad[1]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius or h // 2, fill=bg)
    out.alpha_composite(t, (pad[0] - 40, pad[1] - 40 + 3))
    return out


def with_alpha(layer, a):
    if a >= 1:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda v: int(v * clamp(a))))
    return out


def place(img, layer, cx, cy, scale=1.0, alpha=1.0, blur=0.0, rot=0.0):
    if alpha <= 0:
        return
    if scale != 1.0:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
                             Image.BICUBIC)
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, expand=True)
    if blur > 0.5:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    layer = with_alpha(layer, alpha)
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def blur_in(img, layer, cx, cy, f, start=0, dur=7, base_scale=1.0):
    """The signature move: word arrives blurred and slightly large, then snaps sharp."""
    t = ease_out((f - start) / dur)
    place(img, layer, cx, cy, base_scale * (1.12 - 0.12 * t), alpha=clamp((f - start + 2) / 3),
          blur=18 * (1 - t))


def solid(color):
    return Image.new("RGBA", (W, H), color + (255,))


def fa_num(n):
    return "".join(FA_DIGITS[int(c)] for c in str(n))


def cover(im, w, h, fy=0.5):
    s = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * s + 1), int(im.height * s + 1)), Image.LANCZOS)
    x = (r.width - w) // 2
    y = int(clamp((r.height - h) * fy, 0, r.height - h))
    return r.crop((x, y, x + w, y + h))


def round_corners(im, r):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=r, fill=255)
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


def drop_shadow(card, strength=0.45, blur=26, dy=24):
    pad = blur * 2
    out = Image.new("RGBA", (card.width + 2 * pad, card.height + 2 * pad + dy), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sh.putalpha(card.getchannel("A").point(lambda v: int(v * strength)))
    out.alpha_composite(sh, (pad, pad + dy))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(card, (pad, pad))
    return out


def safe_guide(img):
    d = ImageDraw.Draw(img)
    d.rectangle((SAFE_SIDE, SAFE_TOP, W - SAFE_SIDE, SAFE_BOTTOM), outline=(255, 0, 0, 255), width=4)
    d.line((W - 100, 1155, W - 100, SAFE_BOTTOM), fill=(255, 0, 0, 255), width=4)


# ---------- graphic backgrounds ----------
def graphic_base(accent=None):
    """Navy gradient + fine grid + vignette, optionally with an accent glow behind the poster."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    top, bot = np.array([18, 32, 56], np.float32), np.array([7, 12, 22], np.float32)
    base = top * (1 - y / H)[..., None] + bot * (y / H)[..., None]
    if accent is not None:
        g = np.exp(-(((x - W / 2) / 520) ** 2 + ((y - 800) / 640) ** 2))
        base += g[..., None] * np.array(accent, np.float32) * 0.28
    # vignette
    v = np.clip(1.15 - np.sqrt(((x - W / 2) / W) ** 2 + ((y - H / 2) / H) ** 2) * 1.1, 0.55, 1)
    base *= v[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    # fine grid
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(grid)
    for gx in range(0, W, 90):
        d.line((gx, 0, gx, H), fill=(255, 255, 255, 14), width=1)
    for gy in range(0, H, 90):
        d.line((0, gy, W, gy), fill=(255, 255, 255, 14), width=1)
    # small crosshair marks on a few intersections (editorial detail)
    for cx, cy in [(90, 270), (990, 270), (90, 1440), (990, 1440)]:
        d.line((cx - 14, cy, cx + 14, cy), fill=(255, 255, 255, 90), width=2)
        d.line((cx, cy - 14, cx, cy + 14), fill=(255, 255, 255, 90), width=2)
    img.alpha_composite(grid)
    return img


def outline_text(s, size, colour, alpha, width=3):
    """Stroke-only text layer (outlined type), Latin."""
    f = rubik(size)
    b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), s, font=f)
    m = Image.new("L", (b[2] - b[0] + 20, b[3] - b[1] + 20), 0)
    ImageDraw.Draw(m).text((10 - b[0], 10 - b[1]), s, font=f, fill=255)
    ring = np.array(m.filter(ImageFilter.MaxFilter(2 * width + 1))).astype(int) - np.array(
        m.filter(ImageFilter.MinFilter(3))).astype(int)
    out = Image.new("RGBA", m.size, colour + (0,))
    out.putalpha(Image.fromarray(np.clip(ring * alpha / 255, 0, 255).astype(np.uint8)))
    return out


def marquee_strip(word, size, colour, alpha):
    unit = outline_text(word + "  •  ", size, colour, alpha)
    reps = int(np.ceil((W * 2 + unit.width) / unit.width)) + 1
    strip = Image.new("RGBA", (unit.width * reps, unit.height), (0, 0, 0, 0))
    for r in range(reps):
        strip.alpha_composite(unit, (r * unit.width, 0))
    return strip, unit.width


def draw_marquee(img, strip, unit_w, y, f, speed):
    off = int((f * speed) % unit_w)
    if speed < 0:
        off = unit_w - int((-f * speed) % unit_w)
    img.alpha_composite(strip.crop((off, 0, off + W, strip.height)), (0, int(y - strip.height / 2)))


def progress(img, i, f, accent):
    """Seven-segment progress bar under the counter."""
    d = ImageDraw.Draw(img)
    seg, gap = 52, 10
    total = 7 * seg + 6 * gap
    x0, y = W / 2 - total / 2, 392
    for k in range(7):
        x = x0 + k * (seg + gap)
        d.rounded_rectangle((x, y, x + seg, y + 10), 5, fill=(255, 255, 255, 50))
        fill = 1.0 if k < i else (ease_out(f / 30) if k == i else 0)
        if fill > 0:
            d.rounded_rectangle((x, y, x + seg * fill, y + 10), 5, fill=accent + (255,))


# ---------- prebuilt assets ----------
POSTERS = [Image.open(A / "posters" / p).convert("RGB") for p, *_ in SERIES]
POSTER_H = 760
POSTER_CY = 430 + POSTER_H // 2
CARDS = [drop_shadow(round_corners(p.resize((int(p.width * POSTER_H / p.height), POSTER_H),
                                            Image.LANCZOS), 30)) for p in POSTERS]
LOGO = Image.open(A / "sazan-logo.png").convert("RGBA")
BG_PLAIN = graphic_base()
BG_ACCENT = {CYAN: graphic_base(CYAN), ORANGE: graphic_base(ORANGE)}
MARQ = [(marquee_strip(en, 200, WHITE, 38), marquee_strip(en, 200, WHITE, 22)) for _, en, _, _ in SERIES]

# ---------- hook: "این ۷ سریال رو ببینی / دیگه / دانشگاه / نیاز نداری." ----------
FLASH = [cover(p, W, H, 0.3) for p in POSTERS]
def two_tone_line(parts, size):
    """RTL line made of (text, colour) parts, first part on the right, tight word spacing."""
    f = rubik(size)
    space = int(size * 0.28)
    layers = [text_layer(t, f, c) for t, c in parts]
    asc = max(l.height for l in layers)
    w = sum(l.width - 80 for l in layers) + space * (len(layers) - 1) + 80
    line = Image.new("RGBA", (w, asc), (0, 0, 0, 0))
    x = w - 40
    for l in layers:
        x -= l.width - 80
        # align on the font baseline: same font/size, so same top padding works
        line.alpha_composite(l, (x - 40, 0))
        x -= space
    return line


def baseline_layer(s, size, colour):
    """Text drawn from the font's ascender, so lines of the same size share a baseline."""
    f = rubik(size)
    asc, desc = f.getmetrics()
    w = int(f.getlength(s, direction="rtl", language="fa")) + 40
    layer = Image.new("RGBA", (w, asc + desc), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20, 0), s, font=f, fill=colour, direction="rtl", language="fa")
    return layer


def hook_line(parts, size):
    f = rubik(size)
    space = int(f.getlength(" "))
    layers = [baseline_layer(t, size, c) for t, c in parts]
    w = sum(l.width - 40 for l in layers) + space * (len(layers) - 1) + 40
    line = Image.new("RGBA", (w, layers[0].height), (0, 0, 0, 0))
    x = w - 20
    for l in layers:
        x -= l.width - 40
        line.alpha_composite(l, (x - 20, 0))
        x -= space
    return line


L_LINE1 = hook_line([("این", CREAM), ("۷ سریال", CYAN)], 170)
L_LINE2 = hook_line([("رو ببینی...", CREAM)], 170)
L_DIGE = text_layer("دیگه", rubik(260), CREAM)
L_DANESHGAH = text_layer("دانشگاه", rubik(250), NAVY)
L_NIAZ = text_layer("نیاز نداری.", rubik(220), ORANGE)


def flash_bg(f):
    """Posters flash-cut behind the first beat, two frames each, heavily darkened."""
    p = FLASH[(f // 2) % len(FLASH)].convert("RGBA")
    img = p.filter(ImageFilter.GaussianBlur(6))
    img.alpha_composite(Image.new("RGBA", (W, H), (7, 12, 22, 200)))
    grid = BG_PLAIN.copy()
    grid.putalpha(110)
    img.alpha_composite(grid)
    return img


def frame_hook(f):
    k, local = divmod(f, BEAT)
    if k == 0:
        img = flash_bg(f)
        # everything readable on frame 0: small / giant / small, the giant one punches in
        punch = 1.06 - 0.06 * ease_back(local / 5, 2.0)
        lh = int(L_LINE1.height * 0.82)          # tight, even leading between the two lines
        place(img, L_LINE1, W / 2, 860 - lh / 2, punch)
        place(img, L_LINE2, W / 2, 860 + lh / 2, punch)
    elif k == 1:
        img = BG_ACCENT[CYAN].copy()
        blur_in(img, L_DIGE, W / 2, 860, local, dur=5)
    elif k == 2:
        img = solid(CREAM)
        blur_in(img, L_DANESHGAH, W / 2, 860, local, dur=5)
        p = ease_out((local - 3) / 5)
        if p > 0:   # orange strike through "university"
            d = ImageDraw.Draw(img)
            d.line((W / 2 + 330, 845, W / 2 + 330 - 660 * p, 890), fill=ORANGE, width=26)
    else:
        img = BG_ACCENT[ORANGE].copy()
        blur_in(img, L_NIAZ, W / 2, 860, local, dur=5)
    return img


# ---------- series ----------
L_FA = [fa for _, _, fa, _ in SERIES]
L_LESSON = [ls for *_, ls in SERIES]


def text_on(bg):
    return NAVY if bg == CREAM else CREAM


def counter(img, i, f, colour):
    """Rolling digit (slot-machine roll from the previous number) + static /7."""
    big = rubik(170)
    roll = ease_in_out(f / 8)
    win_h = 190
    col = Image.new("RGBA", (180, win_h * 2), (0, 0, 0, 0))
    prev = text_layer(fa_num(i) if i > 0 else "", big, colour)
    cur = text_layer(fa_num(i + 1), big, colour)
    col.alpha_composite(cur, ((180 - cur.width) // 2, (win_h - cur.height) // 2))
    if prev.width > 80:
        col.alpha_composite(prev, ((180 - prev.width) // 2, win_h + (win_h - prev.height) // 2))
    y = int(win_h * (1 - roll))
    window = col.crop((0, y, 180, y + win_h))
    img.alpha_composite(window, (int(W / 2 - 60 - 90), 285 - win_h // 2))
    of = text_layer("/" + fa_num(len(SERIES)), rubik(64), colour[:3] + (150,) if len(colour) == 3 else colour,
                    rtl=False)
    place(img, of, W / 2 + 70, 300)


def frame_series(i, f):
    fg = CREAM
    accent = CYAN if i % 2 == 0 else ORANGE
    img = BG_ACCENT[accent].copy()
    (top, uw), (bot, uw2) = MARQ[i]
    draw_marquee(img, top, uw, 560, f, 6)
    draw_marquee(img, bot, uw2, 1030, f, -6)

    counter(img, i, f, accent)
    progress(img, i, f, accent)

    # poster: blur-in, scale settle, slight rotation that straightens
    t = ease_back(f / 9, 1.3)
    blur = 22 * (1 - ease_out(f / 6))
    rot = 4 * (1 - ease_out(f / 9)) * (1 if i % 2 else -1)
    drift = 1.0 + 0.035 * (f / EACH_F)
    place(img, CARDS[i], W / 2, POSTER_CY, (0.86 + 0.14 * t) * drift,
          alpha=clamp((f + 2) / 3), blur=blur, rot=rot)

    # lesson as a highlighted pill, words blur in
    pill = pill_layer(L_LESSON[i], rubik(50, "Bold"), accent, NAVY if accent == CYAN else NAVY)
    blur_in(img, pill, W / 2, 1222, f, start=3, dur=6)
    en = text_layer(SERIES[i][1], rubik(68), fg, rtl=False)
    blur_in(img, en, W / 2, 1330, f, start=5, dur=6)
    fa = text_layer(L_FA[i], rubik(42, "Medium"), fg)
    blur_in(img, fa, W / 2, 1410, f, start=7, dur=6)
    return img


# ---------- save card ----------
GW, GH, GAP = 220, 330, 20
GRID = [drop_shadow(round_corners(cover(p, GW, GH), 18), 0.35, 14, 10) for p in POSTERS]


def bookmark(size, fill, outline=None, width=8):
    w, h = size, int(size * 1.3)
    im = Image.new("RGBA", (w + 2 * width, h + 2 * width), (0, 0, 0, 0))
    pts = [(width, width), (w + width, width), (w + width, h + width), (w / 2 + width, h * 0.72 + width),
           (width, h + width)]
    d = ImageDraw.Draw(im)
    if fill:
        d.polygon(pts, fill=fill)
    if outline:
        d.line(pts + [pts[0]], fill=outline, width=width, joint="curve")
    return im


def cursor(size=90):
    im = Image.new("RGBA", (size, int(size * 1.4)), (0, 0, 0, 0))
    s = size / 90
    pts = [(10, 6), (10, 100), (34, 78), (52, 118), (68, 110), (50, 72), (82, 72)]
    pts = [(x * s, y * s) for x, y in pts]
    d = ImageDraw.Draw(im)
    d.polygon(pts, fill=WHITE)
    d.line(pts + [pts[0]], fill=NAVY, width=max(3, int(5 * s)), joint="curve")
    return im


L_SAVE_TITLE = text_layer("سیوش کن", rubik(150), CREAM)
L_SAVE_SUB = text_layer("که بعداً گمش نکنی", rubik(52, "Medium"), CREAM)
CURSOR = cursor()


def save_button(pressed):
    w, h = 470, 130
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=ORANGE if pressed else CREAM)
    label = text_layer("ذخیره شد" if pressed else "ذخیره", rubik(54, "Bold"), NAVY)
    bm = bookmark(46, NAVY if pressed else None, None if pressed else NAVY, 7)
    total = label.width - 80 + 26 + bm.width
    x = (w - total) // 2
    im.alpha_composite(bm, (x, (h - bm.height) // 2))
    im.alpha_composite(label, (x + bm.width + 26 - 40, (h - label.height) // 2 + 3))
    return im


BTN = [save_button(False), save_button(True)]


def frame_save(f):
    img = BG_PLAIN.copy()
    rows = [[0, 1, 2, 3], [4, 5, 6]]
    y0 = 290 + GH // 2
    k = 0
    for r, row in enumerate(rows):
        total = len(row) * GW + (len(row) - 1) * GAP
        x0 = (W - total) // 2 + GW // 2
        for j, idx in enumerate(row):
            start = k * 2 - 2
            k += 1
            t = (f - start) / 7
            if t <= 0:
                continue
            e = ease_back(t, 1.6)
            place(img, GRID[idx], x0 + j * (GW + GAP), y0 + r * (GH + GAP) + 90 * (1 - e),
                  0.75 + 0.25 * e, alpha=clamp(t * 2.5), blur=10 * (1 - ease_out(t)))
    blur_in(img, L_SAVE_TITLE, W / 2, 1075, f, start=10, dur=7)
    blur_in(img, L_SAVE_SUB, W / 2, 1180, f, start=13, dur=7)

    # button arrives, cursor glides in and taps it
    tap = 36
    pressed = f >= tap
    if f >= 16:
        bump = 1 - 0.08 * math.sin(math.pi * clamp((f - tap) / 5)) if f >= tap else 1
        blur_in(img, BTN[1 if pressed else 0], W / 2, 1345, f, start=16, dur=6,
                base_scale=bump)
    if 22 <= f:
        p = ease_in_out((f - 22) / 13)
        cx = W / 2 + 330 * (1 - p) + 60
        cy = 1345 + 260 * (1 - p) + 20
        sc = 0.85 if tap <= f < tap + 4 else 1.0
        place(img, CURSOR, cx, cy, sc, alpha=clamp((f - 22) / 4) * (1 - clamp((f - 46) / 6)))
    return img


# ---------- outro ----------
def logo_for_dark(logo):
    """Recolour the grey tagline to cream so it reads on the dark background."""
    arr = np.array(logo).astype(int)
    rgb = arr[:, :, :3]
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    grey = (sat < 40) & (arr[:, :, 3] > 0)
    arr[grey, 0], arr[grey, 1], arr[grey, 2] = CREAM
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


LOGO_D = logo_for_dark(LOGO)
MARK_W, WORD_X = 383, 428          # alpha gap between the S mark and the wordmark
MARK = LOGO_D.crop((0, 0, MARK_W, LOGO_D.height))
WORD = LOGO_D.crop((WORD_X, 0, LOGO_D.width, LOGO_D.height))
LOGO_S = 0.78                      # final logo scale (about 860px wide)
LOGO_CY = 860
L_HANDLE = text_layer(HANDLE, rubik(46, "Medium"), CREAM, rtl=False)


def frame_outro(f):
    img = solid(NAVY)
    s = LOGO_S
    full_w = LOGO_D.width * s
    left = W / 2 - full_w / 2
    mark_final_x = left + MARK_W * s / 2
    word_final_x = left + (WORD_X + WORD.width / 2) * s


    # 2. the S mark spins in at the centre with an overshoot
    pop = ease_back(f / 12, 1.8)
    spin = 200 * (1 - ease_out(f / 14))
    # 3. then glides left to make room for the wordmark
    slide = ease_in_out((f - 12) / 12)
    mx = W / 2 + (mark_final_x - W / 2) * slide
    mscale = s * (1.35 - 0.35 * slide) * max(0.01, pop)

    # 4. wordmark reveals left to right out of the mark, with a short blur
    if f >= 17:
        r = ease_out((f - 17) / 11)
        word = WORD.resize((int(WORD.width * s), int(WORD.height * s)), Image.LANCZOS)
        m = Image.new("L", word.size, 0)
        ImageDraw.Draw(m).rectangle((0, 0, int(word.width * r), word.height), fill=255)
        # never let the wordmark show through the gaps of the S mark
        wx = word_final_x - 40 * (1 - r) - word.width / 2
        hide = int(mx + MARK_W * mscale / 2 + 6 - wx)
        if hide > 0:
            ImageDraw.Draw(m).rectangle((0, 0, hide, word.height), fill=0)
        word.putalpha(Image.fromarray(np.minimum(np.array(word.getchannel("A")), np.array(m))))
        place(img, word, word_final_x - 40 * (1 - r), LOGO_CY, 1.0, blur=10 * (1 - r))

    # the mark is drawn on top so the wordmark appears to come out from behind it
    place(img, MARK, mx, LOGO_CY, mscale, alpha=clamp(f / 3), rot=spin, blur=8 * (1 - ease_out(f / 8)))

    # 5. light sweep across the finished logo
    if 30 <= f < 46:
        t = (f - 30) / 16
        band = Image.new("L", (W, H), 0)
        x = left - 200 + (full_w + 400) * t
        ImageDraw.Draw(band).polygon([(x, LOGO_CY - 200), (x + 70, LOGO_CY - 200),
                                      (x - 30, LOGO_CY + 200), (x - 100, LOGO_CY + 200)], fill=150)
        band = band.filter(ImageFilter.GaussianBlur(14))
        logo_alpha = Image.new("L", (W, H), 0)
        ls = LOGO_D.resize((int(LOGO_D.width * s), int(LOGO_D.height * s)))
        logo_alpha.paste(ls.getchannel("A"), (int(left), int(LOGO_CY - ls.height / 2)))
        band = Image.fromarray(np.minimum(np.array(band), np.array(logo_alpha)))
        shine = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        shine.putalpha(band)
        img.alpha_composite(shine)

    # 6. handle and an accent rule
    blur_in(img, L_HANDLE, W / 2, 1110, f, start=24, dur=8)
    p = ease_out((f - 28) / 12)
    if p > 0:
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((W / 2 - 170 * p, 1180, W / 2 + 170 * p, 1188), 4, fill=CYAN)
        d.ellipse((W / 2 + 170 * p + 14, 1176, W / 2 + 170 * p + 30, 1192), fill=ORANGE)
    return img


def render_frame(n):
    if n < HOOK_F:
        im = frame_hook(n)
    elif n < HOOK_F + EACH_F * len(SERIES):
        m = n - HOOK_F
        im = frame_series(m // EACH_F, m % EACH_F)
    elif n < HOOK_F + EACH_F * len(SERIES) + SAVE_F:
        im = frame_save(n - HOOK_F - EACH_F * len(SERIES))
    else:
        im = frame_outro(n - HOOK_F - EACH_F * len(SERIES) - SAVE_F)
    return im.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--safe", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "renders" / "7-series-v8.mp4"))
    ap.add_argument("--stills")
    ap.add_argument("--audio", default=str(A / "music.wav"), help="wav to lay under the video; 'none' for silent")
    a = ap.parse_args()

    if a.stills:
        out = ROOT / "work"
        out.mkdir(exist_ok=True)
        for n in map(int, a.stills.split(",")):
            im = render_frame(n)
            if a.safe:
                safe_guide(im)
            im.save(out / f"still_{n:03d}.png")
        return

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           *(["-i", a.audio] if a.audio != "none" else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]),
           "-map", "0:v", "-map", "1:a", "-shortest",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "192k", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(TOTAL):
        im = render_frame(n)
        if a.safe:
            safe_guide(im)
        p.stdin.write(im.tobytes())
    p.stdin.close()
    p.wait()
    print(f"wrote {a.out}  ({TOTAL} frames, {TOTAL / FPS:.2f}s)")


if __name__ == "__main__":
    main()
