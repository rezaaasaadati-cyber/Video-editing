"""Reel cover (1080x1920), v2, matched to the page's current covers:
- dark background, olive glow from the left, big blurred stock-board digits top right
- a symbolic object top left behind the people (here: a film strip with three series stills)
- cut-out people large in the frame, heads in the upper half, bodies running off the bottom
- off-white title: Persian in Aref Ruqaa (closest free match to the covers' calligraphic
  title face), Latin in DM Serif Display (matches "STOMP?")
- slanted orange-to-red bar with the subtitle in Estedad Bold

Source images are high resolution (3840x2160 series art from TVmaze), so nothing is upscaled.
Usage: python3 cover.py [out.jpg]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
A = ROOT / "assets"
W, H = 1080, 1920
OFF_WHITE = (243, 237, 228)


def fnt(name, size):
    return ImageFont.truetype(str(A / "fonts" / name), size)


def background():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32) + np.array([8, 10, 9], np.float32)
    g = np.exp(-(((x + 100) / 800) ** 2 + ((y - 700) / 950) ** 2))
    base += g[..., None] * np.array([92, 100, 6], np.float32)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")

    board = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(board)
    f = fnt("Anton-Regular.ttf", 150)
    for row in range(8):
        yy = -40 + row * 175
        d.text((620, yy), "1,000", font=f, fill=(30, 150, 120, 120))
        d.text((1010, yy), "3", font=f, fill=(200, 35, 45, 140))
    board = board.filter(ImageFilter.GaussianBlur(7))
    fade = np.clip(1.25 - np.linspace(0, 1, H) * 1.6, 0, 1)
    a = np.array(board.getchannel("A")).astype(np.float32) * fade[:, None]
    board.putalpha(Image.fromarray(a.astype(np.uint8)))
    img.alpha_composite(board)
    return img


def film_strip(stills, frame_w=420, frame_h=290):
    """A 35mm-style strip holding the given stills, returned as RGBA."""
    gap, edge = 26, 70
    w = edge * 2 + frame_w
    h = len(stills) * (frame_h + gap) + gap
    strip = Image.new("RGBA", (w, h), (18, 18, 20, 255))
    d = ImageDraw.Draw(strip)
    for i, (path, box) in enumerate(stills):
        im = Image.open(path).convert("RGB").crop(box)
        s = max(frame_w / im.width, frame_h / im.height)
        im = im.resize((int(im.width * s + 1), int(im.height * s + 1)), Image.LANCZOS)
        im = im.crop(((im.width - frame_w) // 2, (im.height - frame_h) // 2,
                      (im.width - frame_w) // 2 + frame_w, (im.height - frame_h) // 2 + frame_h))
        strip.paste(im, (edge, gap + i * (frame_h + gap)))
    for y in range(14, h - 20, 44):
        for x in (22, w - 22 - 26):
            d.rounded_rectangle((x, y, x + 26, y + 20), 5, fill=(235, 232, 225, 255))
    # glossy highlight
    gl = Image.new("L", (w, h), 0)
    ImageDraw.Draw(gl).polygon([(0, 0), (w * 0.45, 0), (0, h * 0.35)], fill=40)
    hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    hl.putalpha(gl.filter(ImageFilter.GaussianBlur(30)))
    strip.alpha_composite(hl)
    return strip


def shadow_paste(img, layer, x, y, blur=28, alpha=0.65, off=(10, 22)):
    pad = blur * 3
    sh = Image.new("RGBA", (layer.width + 2 * pad, layer.height + 2 * pad), (0, 0, 0, 0))
    s = Image.new("RGBA", layer.size, (0, 0, 0, 255))
    s.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    sh.alpha_composite(s, (pad, pad))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(sh, (int(x - pad + off[0]), int(y - pad + off[1])))
    img.alpha_composite(layer, (int(x), int(y)))


def text_layer(s, f, fill, rtl=True):
    kw = {"direction": "rtl", "language": "fa"} if rtl else {}
    b = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), s, font=f, **kw)
    layer = Image.new("RGBA", (b[2] - b[0] + 40, b[3] - b[1] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((20 - b[0], 20 - b[1]), s, font=f, fill=fill, **kw)
    return layer, -b[1] + 20  # layer, y of the text origin inside the layer


def title(img, cy):
    """'MBA' (serif) on the right, 'نخون!' (Ruqaa) on the left, as one RTL line."""
    fa, fa_top = text_layer("نخون!", fnt("ArefRuqaa-Bold.ttf", 250), OFF_WHITE)
    en, en_top = text_layer("MBA", fnt("DMSerifDisplay-Regular.ttf", 210), OFF_WHITE, rtl=False)
    gap = 10
    total = fa.width + en.width + gap
    x0 = (W - total) / 2
    row = Image.new("RGBA", (int(total), max(fa.height, en.height) + 60), (0, 0, 0, 0))
    # align the Latin baseline with the Persian main line
    row.alpha_composite(fa, (0, 0))
    row.alpha_composite(en, (fa.width + gap, int(fa.height * 0.5 - en.height * 0.5) - 8))
    shadow_paste(img, row, x0, cy - row.height / 2, blur=16, alpha=0.75, off=(0, 8))


def slanted_bar(img, s, cy, angle=5.0):
    bw, bh = 1500, 112
    t = np.linspace(0, 1, bw, dtype=np.float32)[None, :, None]
    left, right = np.array([250, 105, 15], np.float32), np.array([205, 22, 38], np.float32)
    grad = (left * (1 - t) + right * t).repeat(bh, axis=0)
    bar = Image.fromarray(grad.astype(np.uint8)).convert("RGBA")
    txt, _ = text_layer(s, fnt("Estedad-Bold.ttf", 54), (255, 255, 255))
    bar.alpha_composite(txt, (int(bw / 2 - txt.width / 2 + 40), int(bh / 2 - txt.height / 2 + 4)))
    bar = bar.rotate(angle, resample=Image.BICUBIC, expand=True)
    shadow_paste(img, bar, W / 2 - bar.width / 2, cy - bar.height / 2, blur=20, alpha=0.5, off=(0, 14))


def bottom_fade(img, start):
    a = np.clip((np.arange(H) - start) / (H - start), 0, 1) ** 1.3 * 235
    layer = Image.new("RGBA", (W, H), (8, 10, 9, 255))
    layer.putalpha(Image.fromarray(np.repeat(a[:, None], W, axis=1).astype(np.uint8)))
    img.alpha_composite(layer)


def main(out):
    img = background()

    # object: film strip with stills from three other series, tilted, running off the top-left
    H_ = A / "hires"
    strip = film_strip([
        (H_ / "389_973816.jpg", (2100, 0, 3700, 1150)),     # Billions
        (H_ / "396_990282.jpg", (1950, 0, 3450, 1050)),     # Mad Men
        (H_ / "219_547612.jpg", (500, 150, 1450, 800)),     # Suits
    ])
    strip = strip.rotate(-28, resample=Image.BICUBIC, expand=True)
    shadow_paste(img, strip, -170, -160, blur=30, alpha=0.7)

    # people: Succession group cut-out, large, heads in the upper half, bleeding off the bottom/right
    people = Image.open(A / "characters" / "succession_group_cut.png")
    s = 1.0
    people = people.resize((int(people.width * s), int(people.height * s)), Image.LANCZOS)
    # keep the eye on the front figure: darken the people layer away from him
    px, py = -60, H - people.height + 40
    yy, xx = np.mgrid[0:people.height, 0:people.width].astype(np.float32)
    dist = np.sqrt(((xx + px - 420) / 1.0) ** 2 + ((yy + py - 650) / 1.6) ** 2)
    k = np.clip(1.0 - (dist - 200) / 330, 0.4, 1.0)[..., None]
    rgb = np.array(people.convert("RGB")).astype(np.float32) * k
    lit = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    lit.putalpha(people.getchannel("A"))
    shadow_paste(img, lit, px, py, blur=40, alpha=0.8, off=(0, 0))

    bottom_fade(img, 1350)
    title(img, 1440)
    slanted_bar(img, "به جاش این ۷ سریال رو ببین.", 1590)

    img.convert("RGB").save(out, quality=95, subsampling=0)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "renders" / "7-series-cover.jpg"))
