"""Render the "7 series = 4 years of MBA" reel (1080x1920, 30fps, silent).

Frames are drawn with Pillow (raqm for Persian shaping) and piped into ffmpeg.
Usage: python3 build.py [--safe] [--out renders/7-series-v1.mp4]
  --safe  draws the Reels safe-zone guide in red (for checking only).
"""
import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
A = ROOT / "assets"
W, H, FPS = 1080, 1920, 30

# Reels safe zone (from the video-edit skill's layout rules)
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 220, 1470, 35

YELLOW = (255, 210, 40)
RED = (230, 45, 35)
ORANGE = (255, 120, 30)
WHITE = (255, 255, 255)
BG_DARK = (10, 14, 12)

SERIES = [
    ("p1.jpg", "Suits", "کت‌وشلواری‌ها", "مذاکره از موضع قدرت"),
    ("p2.jpg", "Succession", "جانشینی", "بازی قدرت در شرکت"),
    ("p3.jpg", "Billions", "میلیاردها", "روانشناسی رقابت"),
    ("p4.jpg", "Mad Men", "مردان دیوانه", "فروش و تبلیغات"),
    ("p5.jpg", "Silicon Valley", "دره سیلیکون", "ساختن استارتاپ از صفر"),
    ("p6.jpg", "Super Pumped", "داستان اوبر", "رشد سریع و هزینه‌اش"),
    ("p7.jpg", "The Dropout", "ترک تحصیل", "دروغ در بیزنس چه می‌کند"),
]
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

# Timeline (frames)
HOOK_F = 45            # 0.0 - 1.5s
EACH_F = 39            # 1.3s per series
END_F = 72             # 2.4s grid + ask
TOTAL = HOOK_F + EACH_F * len(SERIES) + END_F


def font(weight, size):
    return ImageFont.truetype(str(A / "fonts" / f"Vazirmatn-{weight}.ttf"), size)


def fa_num(n):
    return "".join(FA_DIGITS[int(c)] for c in str(n))


def text_w(draw, s, f, rtl=True):
    kw = {"direction": "rtl", "language": "fa"} if rtl else {}
    b = draw.textbbox((0, 0), s, font=f, **kw)
    return b[2] - b[0], b[3] - b[1], b


def draw_center(draw, s, f, cy, fill, rtl=True, stroke=0, stroke_fill=(0, 0, 0)):
    kw = {"direction": "rtl", "language": "fa"} if rtl else {}
    w, h, b = text_w(draw, s, f, rtl)
    x = (W - w) // 2 - b[0]
    y = cy - h // 2 - b[1]
    draw.text((x, y), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, **kw)
    return w, h


def bar_text(img, s, f, cy, bar_fill, txt_fill=WHITE, pad=(34, 16)):
    d = ImageDraw.Draw(img)
    w, h, _ = text_w(d, s, f)
    x0, x1 = (W - w) // 2 - pad[0], (W + w) // 2 + pad[0]
    y0, y1 = cy - h // 2 - pad[1], cy + h // 2 + pad[1] + 6
    d.rounded_rectangle((x0, y0, x1, y1), radius=14, fill=bar_fill)
    draw_center(d, s, f, cy + 3, txt_fill)


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    r = im.resize((int(im.width * s + 1), int(im.height * s + 1)), Image.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def round_corners(im, r):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=r, fill=255)
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


def brand_bg():
    """Dark background with a green/yellow glow, like the page's current covers."""
    bg = Image.new("RGB", (W, H), BG_DARK)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((-300, 1100, 900, 2300), fill=(20, 110, 60))
    g.ellipse((500, -300, 1500, 700), fill=(120, 100, 10))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    return Image.blend(bg, glow, 0.55)


def zoom_blur(frame, strength):
    """Cheap radial zoom blur: average of progressively scaled copies."""
    if strength <= 0.01:
        return frame
    acc = frame.copy()
    n = 5
    for i in range(1, n + 1):
        s = 1 + strength * i / n
        z = frame.resize((int(W * s), int(H * s)), Image.BILINEAR)
        x, y = (z.width - W) // 2, (z.height - H) // 2
        acc = Image.blend(acc, z.crop((x, y, x + W, y + H)), 1 / (i + 1))
    return acc


def ease_out(t):
    return 1 - (1 - t) ** 3


def safe_guide(img):
    d = ImageDraw.Draw(img)
    d.rectangle((SAFE_SIDE, SAFE_TOP, W - SAFE_SIDE, SAFE_BOTTOM), outline=(255, 0, 0), width=4)
    d.line((W - 100, 1155, W - 100, SAFE_BOTTOM), fill=(255, 0, 0), width=4)


# ---------- prebuilt layers ----------
POSTERS = [Image.open(A / "posters" / p).convert("RGB") for p, *_ in SERIES]
BRAND = brand_bg()

POSTER_H = 800
POSTER_TOP = 360


def poster_card(im):
    w = int(im.width * POSTER_H / im.height)
    card = round_corners(im.resize((w, POSTER_H), Image.LANCZOS), 26)
    return card


CARDS = [poster_card(p) for p in POSTERS]
BLUR_BG = []
for p in POSTERS:
    b = cover(p, W, H).filter(ImageFilter.GaussianBlur(40))
    b = Image.blend(b, Image.new("RGB", (W, H), (0, 0, 0)), 0.62)
    BLUR_BG.append(Image.blend(b, BRAND, 0.35))


def hook_collage():
    # 2x2 grid of poster crops focused on the people
    tiles = [(POSTERS[0], 0.42), (POSTERS[1], 0.35), (POSTERS[2], 0.45), (POSTERS[3], 0.45)]
    img = Image.new("RGB", (W, H))
    tw, th = W // 2, H // 2
    for i, (p, fy) in enumerate(tiles):
        s = max(tw / p.width, th / p.height) * 1.25
        r = p.resize((int(p.width * s), int(p.height * s)), Image.LANCZOS)
        x = (r.width - tw) // 2
        y = max(0, min(r.height - th, int(r.height * fy - th / 2)))
        img.paste(r.crop((x, y, x + tw, y + th)), ((i % 2) * tw, (i // 2) * th))
    return img


COLLAGE = hook_collage()


def frame_hook(f):
    t = f / HOOK_F
    s = 1.0 + 0.08 * t
    z = COLLAGE.resize((int(W * s), int(H * s)), Image.BILINEAR)
    x, y = (z.width - W) // 2, (z.height - H) // 2
    img = z.crop((x, y, x + W, y + H))
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    # dark band behind the hook text
    band = Image.new("L", (W, H), 0)
    ImageDraw.Draw(band).rectangle((0, 640, W, 1240), fill=215)
    band = band.filter(ImageFilter.GaussianBlur(60))
    img.paste(Image.new("RGB", (W, H), BG_DARK), (0, 0), band)
    d = ImageDraw.Draw(img)
    pop = ease_out(min(1, f / 6))  # hook text is readable from frame 0, settles in 0.2s
    draw_center(d, "۷ سریال", font("Black", int(190 * (0.9 + 0.1 * pop))), 770, YELLOW)
    draw_center(d, "=", font("Black", 120), 935, WHITE)
    draw_center(d, "۴ سال MBA", font("Black", int(150 * (0.9 + 0.1 * pop))), 1080, WHITE)
    if f >= 12:
        bar_text(img, "+ مذاکره", font("ExtraBold", 54), 1215, RED)
    return img


def frame_series(i, f):
    _, en, fa, lesson = SERIES[i]
    img = BLUR_BG[i].copy()
    t = f / EACH_F
    card = CARDS[i]
    s = 0.94 + 0.08 * ease_out(min(1, f / 8)) + 0.03 * t  # punch in, then slow push
    cw, ch = int(card.width * s), int(card.height * s)
    c = card.resize((cw, ch), Image.BILINEAR)
    cx, cy = W // 2, POSTER_TOP + POSTER_H // 2
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (cx - cw // 2 + 10, cy - ch // 2 + 24, cx + cw // 2 + 10, cy + ch // 2 + 24), 30, fill=170)
    img.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(28)))
    img.paste(c, (cx - cw // 2, cy - ch // 2), c)
    # zoom-blur on the cut, applied to the picture only so the text stays readable
    img = zoom_blur(img, max(0.0, 0.16 * (1 - f / 5)))

    d = ImageDraw.Draw(img)
    # counter, top inside the safe zone
    cnt = f"{fa_num(i + 1)}/{fa_num(len(SERIES))}"
    draw_center(d, cnt, font("Black", 64), 290, YELLOW, stroke=3)
    # lesson bar + names under the poster
    bar_text(img, lesson, font("ExtraBold", 50), 1222, RED if i % 2 == 0 else ORANGE)
    d = ImageDraw.Draw(img)
    draw_center(d, en, font("Black", 62), 1318, WHITE, rtl=False, stroke=2)
    draw_center(d, fa, font("Bold", 46), 1400, (225, 225, 225), stroke=2)
    return img


GRID_CARDS = []
for p in POSTERS:
    gw, gh = 228, 340
    GRID_CARDS.append(round_corners(cover(p, gw, gh), 16))


def frame_end(f):
    img = BRAND.copy()
    d = ImageDraw.Draw(img)
    gw, gh, gap = 228, 340, 22
    rows = [[0, 1, 2, 3], [4, 5, 6]]
    y0 = 300
    k = 0
    for r, row in enumerate(rows):
        total = len(row) * gw + (len(row) - 1) * gap
        x0 = (W - total) // 2
        for j, idx in enumerate(row):
            start = k * 3 - 3  # first card already visible on the cut frame
            t = ease_out(max(0, min(1, (f - start) / 7)))
            k += 1
            if t <= 0:
                continue
            s = 0.6 + 0.4 * t
            c = GRID_CARDS[idx].resize((int(gw * s), int(gh * s)), Image.BILINEAR)
            x = x0 + j * (gw + gap) + (gw - c.width) // 2
            y = y0 + r * (gh + gap) + (gh - c.height) // 2 + int((1 - t) * 60)
            img.paste(c, (x, y), c)
            n = font("Black", 40)
            if t > 0.8:
                bx, by = x0 + j * (gw + gap) + 12, y0 + r * (gh + gap) + 10
                d.rounded_rectangle((bx, by, bx + 56, by + 56), 12, fill=YELLOW)
                nd = fa_num(idx + 1)
                w, h, b = text_w(d, nd, n)
                d.text((bx + 28 - w // 2 - b[0], by + 28 - h // 2 - b[1]), nd, font=n, fill=BG_DARK,
                       direction="rtl", language="fa")
    if f >= 20:
        p = ease_out(min(1, (f - 20) / 8))
        draw_center(d, "سیو کن", font("Black", int(110 * (0.85 + 0.15 * p))), 1145, YELLOW)
        bar_text(img, "که بعداً گمش نکنی", font("ExtraBold", 54), 1290, RED)
        d = ImageDraw.Draw(img)
        draw_center(d, "کدومش رو دیدی؟", font("Bold", 46), 1400, WHITE)
    return img


def render_frame(n):
    if n < HOOK_F:
        return frame_hook(n)
    n -= HOOK_F
    if n < EACH_F * len(SERIES):
        return frame_series(n // EACH_F, n % EACH_F)
    return frame_end(n - EACH_F * len(SERIES))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--safe", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "renders" / "7-series-v1.mp4"))
    ap.add_argument("--stills", help="comma-separated frame numbers to save as PNG instead of rendering")
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
