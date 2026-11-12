"""Render the "MBA nakhoon / 7 series" reel (1080x1920, 30fps, silent), v2.

Frames are drawn with Pillow (raqm for Persian shaping) and piped into ffmpeg.
Usage: python3 build.py [--safe] [--out renders/7-series-v2.mp4] [--stills 0,10,60]
  --safe    draws the Reels safe-zone guide in red (for checking only).
  --stills  saves those frame numbers as PNGs in work/ instead of rendering.

Fonts: Lalezar (Persian display), Estedad (Persian body), Anton (English titles). All OFL.
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

YELLOW = (255, 210, 40)
RED = (232, 40, 35)
ORANGE = (255, 120, 30)
WHITE = (255, 255, 255)
BG_DARK = (10, 14, 12)

SERIES = [
    ("p1.jpg", "SUITS", "کت‌وشلواری‌ها", "مذاکره از موضع قدرت"),
    ("p2.jpg", "SUCCESSION", "جانشینی", "بازی قدرت در شرکت"),
    ("p3.jpg", "BILLIONS", "میلیاردها", "روانشناسی رقابت"),
    ("p4.jpg", "MAD MEN", "مردان دیوانه", "فروش و تبلیغات"),
    ("p5.jpg", "SILICON VALLEY", "دره سیلیکون", "ساختن استارتاپ از صفر"),
    ("p6.jpg", "SUPER PUMPED", "داستان اوبر", "رشد سریع و هزینه‌اش"),
    ("p7.jpg", "THE DROPOUT", "ترک تحصیل", "دروغ در بیزنس چه می‌کند"),
]
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

HOOK_F = 51            # 1.7s
EACH_F = 42            # 1.4s per series
END_F = 72             # 2.4s
TOTAL = HOOK_F + EACH_F * len(SERIES) + END_F

FONTS = {}


def font(name, size):
    key = (name, size)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(str(A / "fonts" / name), size)
    return FONTS[key]


DISPLAY = "Lalezar-Regular.ttf"
BODY = "Estedad-ExtraBold.ttf"
LATIN = "Anton-Regular.ttf"


# ---------- easing ----------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_back(t, k=1.9):
    t = clamp(t) - 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


# ---------- text helpers ----------
def kw(rtl):
    return {"direction": "rtl", "language": "fa"} if rtl else {}


def text_layer(s, f, fill, rtl=True, stroke=0, stroke_fill=(0, 0, 0), shadow=True):
    """Render text to its own RGBA layer (so it can be scaled / moved / masked)."""
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    b = tmp.textbbox((0, 0), s, font=f, stroke_width=stroke, **kw(rtl))
    pad = 30
    w, h = b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((pad - b[0], pad - b[1]), s, font=f, fill=fill, stroke_width=stroke,
           stroke_fill=stroke_fill, **kw(rtl))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(10)).point(lambda v: v * 0.7))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.alpha_composite(sh, (0, 6))
        out.alpha_composite(layer)
        layer = out
    return layer


def bar_layer(s, f, fill, txt=WHITE, pad=(36, 18)):
    t = text_layer(s, f, txt, shadow=False)
    w, h = t.width - 60 + 2 * pad[0], t.height - 60 + 2 * pad[1]
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle((0, 0, w - 1, h - 1), radius=16, fill=fill)
    bar.alpha_composite(t, (pad[0] - 30, pad[1] - 30 + 4))
    return bar


def place(img, layer, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if scale != 1.0:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
                             Image.BICUBIC)
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1.0:
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def wipe(layer, t, rtl=True):
    """Reveal a layer from right to left (Persian reading direction)."""
    t = clamp(t)
    if t >= 1:
        return layer
    w = int(layer.width * t)
    m = Image.new("L", layer.size, 0)
    if w > 0:
        x0 = layer.width - w if rtl else 0
        ImageDraw.Draw(m).rectangle((x0, 0, x0 + w, layer.height), fill=255)
    out = layer.copy()
    out.putalpha(Image.fromarray(np.minimum(np.array(layer.getchannel("A")), np.array(m))))
    return out


def fa_num(n):
    return "".join(FA_DIGITS[int(c)] for c in str(n))


# ---------- image helpers ----------
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


def brand_bg():
    bg = Image.new("RGB", (W, H), BG_DARK)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((-300, 1100, 900, 2300), fill=(20, 110, 60))
    g.ellipse((500, -300, 1500, 700), fill=(120, 100, 10))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    return Image.blend(bg, glow, 0.55).convert("RGBA")


def perspective_coeffs(dst, src):
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, dtype=float)
    b = np.array(src, dtype=float).reshape(8)
    return np.linalg.solve(a, b).tolist()


def tilt_y(card, angle_deg):
    """Rotate an RGBA card around its vertical axis (fake 3D)."""
    if abs(angle_deg) < 0.3:
        return card, 0
    a = math.radians(angle_deg)
    w, h = card.size
    hw = w / 2 * math.cos(a)
    d = 0.35 * math.sin(a)  # perspective: near edge grows, far edge shrinks
    ow = int(w * 1.0)
    oh = int(h * (1 + abs(d)) + 2)
    cx, cy = ow / 2, oh / 2
    lh, rh = h / 2 * (1 + d), h / 2 * (1 - d)
    dst = [(cx - hw, cy - lh), (cx + hw, cy - rh), (cx + hw, cy + rh), (cx - hw, cy + lh)]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    out = card.transform((ow, oh), Image.PERSPECTIVE, perspective_coeffs(dst, src), Image.BICUBIC)
    return out, (oh - h) // 2


def motion_blur_x(layer, amount):
    if amount < 2:
        return layer
    k = int(amount)
    acc = np.zeros((layer.height, layer.width, 4), dtype=np.float32)
    arr = np.array(layer, dtype=np.float32)
    n = 6
    for i in range(n):
        acc += np.roll(arr, int(-k * i / n), axis=1)
    return Image.fromarray((acc / n).astype(np.uint8), "RGBA")


def shine(card, t):
    """Diagonal light sweep across a card, t in 0..1."""
    w, h = card.size
    band = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(band)
    x = -w * 0.6 + t * w * 2.2
    d.polygon([(x, 0), (x + 90, 0), (x + 90 - h * 0.35, h), (x - h * 0.35, h)], fill=110)
    band = band.filter(ImageFilter.GaussianBlur(18))
    band = Image.fromarray(np.minimum(np.array(band), np.array(card.getchannel("A"))))
    white = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    white.putalpha(band)
    out = card.copy()
    out.alpha_composite(white)
    return out


def safe_guide(img):
    d = ImageDraw.Draw(img)
    d.rectangle((SAFE_SIDE, SAFE_TOP, W - SAFE_SIDE, SAFE_BOTTOM), outline=(255, 0, 0, 255), width=4)
    d.line((W - 100, 1155, W - 100, SAFE_BOTTOM), fill=(255, 0, 0, 255), width=4)


# ---------- prebuilt layers ----------
POSTERS = [Image.open(A / "posters" / p).convert("RGB") for p, *_ in SERIES]
BRAND = brand_bg()
POSTER_H = 780
POSTER_CY = 380 + POSTER_H // 2
CARDS = [round_corners(p.resize((int(p.width * POSTER_H / p.height), POSTER_H), Image.LANCZOS), 28)
         for p in POSTERS]
BLUR_BG = []
for p in POSTERS:
    b = cover(p, W, H).filter(ImageFilter.GaussianBlur(45))
    b = Image.blend(b, Image.new("RGB", (W, H), (0, 0, 0)), 0.6)
    BLUR_BG.append(Image.blend(b.convert("RGBA"), BRAND, 0.35))

# hook
COLLAGE_TILES = [(POSTERS[0], 0.40), (POSTERS[1], 0.33), (POSTERS[2], 0.45), (POSTERS[3], 0.40)]


def build_collage():
    img = Image.new("RGB", (W + 200, H + 200))
    tw, th = (W + 200) // 2, (H + 200) // 2
    for i, (p, fy) in enumerate(COLLAGE_TILES):
        img.paste(cover(p, tw, th, fy), ((i % 2) * tw, (i // 2) * th))
    dark = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, dark, 0.58).convert("RGBA")


COLLAGE = build_collage()
L_MBA = text_layer("MBA", font(LATIN, 330), WHITE, rtl=False)
L_NAKHOON = text_layer("نخون!", font(DISPLAY, 250), YELLOW)
L_SUB = bar_layer("این ۷ تا سریال رو ببین", font(BODY, 58), RED)


def frame_hook(f):
    t = f / HOOK_F
    # background: slow push + drift
    s = 1.0 + 0.06 * t
    z = COLLAGE.resize((int(COLLAGE.width * s), int(COLLAGE.height * s)), Image.BILINEAR)
    ox = (z.width - W) // 2 + int(40 * t)
    oy = (z.height - H) // 2
    img = z.crop((ox, oy, ox + W, oy + H))
    band = Image.new("L", (W, H), 0)
    ImageDraw.Draw(band).rectangle((0, 560, W, 1330), fill=200)
    img.alpha_composite(Image.new("RGBA", (W, H), BG_DARK + (0,)), (0, 0))
    dark = Image.new("RGBA", (W, H), BG_DARK + (255,))
    dark.putalpha(band.filter(ImageFilter.GaussianBlur(70)))
    img.alpha_composite(dark)

    # slam-in with a short camera shake (text readable from frame 0)
    slam = ease_back(f / 6, 2.2)
    sc = 1.25 - 0.25 * slam
    shake = (6 - f) * 4 if f < 6 else 0
    sx = shake * math.sin(f * 2.1)
    sy = shake * math.cos(f * 1.7)
    place(img, L_MBA, W / 2 + sx, 760 + sy, sc)
    nk = ease_back((f - 3) / 7, 2.0) if f >= 3 else 0.0
    place(img, L_NAKHOON, W / 2 + sx, 1010 + sy, 1.25 - 0.25 * nk if f >= 3 else 1.25,
          alpha=clamp((f - 1) / 3) if f < 4 else 1.0, rot=-3 * (1 - nk) + 2)

    # red strike through MBA
    if f >= 9:
        p = ease_out(clamp((f - 9) / 6))
        d = ImageDraw.Draw(img)
        x0, x1 = W / 2 - 290, W / 2 - 290 + 580 * p
        d.line((x0, 790 + sy, x1, 735 + sy - 0 * p), fill=RED, width=26)

    # sub line slides up
    if f >= 16:
        p = ease_out(clamp((f - 16) / 7))
        place(img, L_SUB, W / 2, 1250 + 60 * (1 - p), alpha=p)
    return img


# series
L_EN = [text_layer(en, font(LATIN, 92), WHITE, rtl=False) for _, en, _, _ in SERIES]
L_FA = [text_layer(fa, font(BODY, 44), (230, 230, 230)) for _, _, fa, _ in SERIES]
L_LESSON = [bar_layer(ls, font(BODY, 50), RED if i % 2 == 0 else ORANGE)
            for i, (_, _, _, ls) in enumerate(SERIES)]
L_NUM = [text_layer(fa_num(i + 1), font(DISPLAY, 150), YELLOW) for i in range(len(SERIES))]
L_OF = text_layer("/" + fa_num(len(SERIES)), font(DISPLAY, 70), (255, 255, 255, 200), rtl=False)


def frame_series(i, f):
    img = BLUR_BG[i].copy()
    # background breathes slightly
    # card: whip in from the right with a 3D swing, then slow push
    p = clamp(0.3 + 0.7 * f / 9)  # card is already on screen on the cut frame
    e = ease_back(p, 1.4)
    angle = -55 * (1 - e)
    x_off = 520 * (1 - ease_out(p))
    scale = 0.96 + 0.05 * (f / EACH_F)
    card = CARDS[i]
    if f > 12:
        card = shine(card, clamp((f - 12) / 18))
    if scale != 1.0:
        card = card.resize((int(card.width * scale), int(card.height * scale)), Image.BICUBIC)
    card, dy = tilt_y(card, angle)
    card = motion_blur_x(card, 90 * (1 - ease_out(p)) if f < 6 else 0)
    cx = W / 2 + x_off
    # shadow
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sh.putalpha(card.getchannel("A").point(lambda v: int(v * 0.65)))
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    img.alpha_composite(sh, (int(cx - card.width / 2 + 14), int(POSTER_CY - card.height / 2 + 28)))
    img.alpha_composite(card, (int(cx - card.width / 2), int(POSTER_CY - card.height / 2)))

    # flash on the cut
    if f < 2:
        img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, 90 if f == 0 else 35)))

    # counter: big number pops, "/7" beside it
    n = ease_back(clamp(f / 6), 2.4)
    # reads "1/7" left to right, as Persian digits are written
    place(img, L_NUM[i], W / 2 - 40, 290, 0.6 + 0.4 * n)
    place(img, L_OF, W / 2 + 45, 305, alpha=clamp(f / 4))

    # lesson bar wipes in right-to-left, names rise
    place(img, wipe(L_LESSON[i], ease_out(clamp((f - 3) / 7))), W / 2, 1218)
    pe = ease_out(clamp((f - 5) / 7))
    place(img, L_EN[i], W / 2, 1330 + 40 * (1 - pe), alpha=pe)
    pf = ease_out(clamp((f - 7) / 7))
    place(img, L_FA[i], W / 2, 1420 + 30 * (1 - pf), alpha=pf)
    return img


# end card
GW, GH, GAP = 228, 340, 22
GRID_CARDS = [round_corners(cover(p, GW, GH), 18) for p in POSTERS]
L_GRID_NUM = [text_layer(fa_num(i + 1), font(DISPLAY, 46), BG_DARK, shadow=False) for i in range(7)]
L_SAVE = text_layer("سیوش کن", font(DISPLAY, 170), YELLOW)
L_SAVE_SUB = bar_layer("که بعداً گمش نکنی", font(BODY, 52), RED)
L_ASK = text_layer("کدومش رو دیدی؟", font(BODY, 46), WHITE)


def bookmark(size, fill):
    w, h = size, int(size * 1.3)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).polygon([(0, 0), (w, 0), (w, h), (w / 2, h * 0.72), (0, h)], fill=fill)
    return im


L_BOOKMARK = bookmark(70, YELLOW)


def frame_end(f):
    img = BRAND.copy()
    rows = [[0, 1, 2, 3], [4, 5, 6]]
    y0 = 300
    k = 0
    for r, row in enumerate(rows):
        total = len(row) * GW + (len(row) - 1) * GAP
        x0 = (W - total) // 2
        for j, idx in enumerate(row):
            start = k * 3 - 3
            k += 1
            t = clamp((f - start) / 8)
            if t <= 0:
                continue
            e = ease_back(t, 1.8)
            cx = x0 + j * (GW + GAP) + GW / 2
            cy = y0 + r * (GH + GAP) + GH / 2 - 140 * (1 - e)
            c = GRID_CARDS[idx]
            place(img, c, cx, cy, 0.7 + 0.3 * e, alpha=clamp(t * 2), rot=8 * (1 - e) * (1 if j % 2 else -1))
            if t > 0.7:
                d = ImageDraw.Draw(img)
                bx, by = cx - GW / 2 + 12, cy - GH / 2 + 10
                d.rounded_rectangle((bx, by, bx + 58, by + 58), 12, fill=YELLOW)
                place(img, L_GRID_NUM[idx], bx + 29, by + 31)
    if f >= 20:
        p = ease_back(clamp((f - 20) / 7), 2.2)
        pulse = 1 + 0.04 * math.sin((f - 27) / 5) if f > 27 else 1
        sc = (0.6 + 0.4 * p) * pulse
        place(img, L_SAVE, W / 2 + 45, 1120, sc)
        # bookmark icon sits left of the (right-to-left) text
        place(img, L_BOOKMARK, W / 2 + 45 - (L_SAVE.width - 60) * sc / 2 - 70, 1125, sc, rot=-8)
    if f >= 26:
        place(img, wipe(L_SAVE_SUB, ease_out(clamp((f - 26) / 7))), W / 2, 1290)
    if f >= 32:
        pa = ease_out(clamp((f - 32) / 6))
        place(img, L_ASK, W / 2, 1405 + 20 * (1 - pa), alpha=pa)
    return img


def render_frame(n):
    if n < HOOK_F:
        im = frame_hook(n)
    elif n < HOOK_F + EACH_F * len(SERIES):
        m = n - HOOK_F
        im = frame_series(m // EACH_F, m % EACH_F)
    else:
        im = frame_end(n - HOOK_F - EACH_F * len(SERIES))
    return im.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--safe", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "renders" / "7-series-v2.mp4"))
    ap.add_argument("--stills")
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
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
           "-map", "0:v", "-map", "1:a", "-shortest",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "128k", a.out]
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
