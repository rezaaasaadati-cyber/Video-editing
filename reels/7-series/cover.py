"""Reel cover (1080x1920) in the page's current cover style: dark background with an olive
glow and a blurred stock-board, cut-out people, a symbolic object on top, a big white title
and a slanted orange-to-red bar. Title stays inside the 4:5 grid crop (y 285-1635).

Usage: python3 cover.py [out.jpg]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).parent
A = ROOT / "assets"
W, H = 1080, 1920
FONT = A / "fonts" / "Rubik[wght].ttf"


def rubik(size, weight="Black"):
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_name(weight)
    return f


def background():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32) + np.array([10, 13, 11], np.float32)
    # olive / yellow-green glow from the left, like the page's covers
    g = np.exp(-(((x + 150) / 900) ** 2 + ((y - 800) / 900) ** 2))
    base += g[..., None] * np.array([95, 105, 10], np.float32)
    g2 = np.exp(-(((x - 200) / 500) ** 2 + ((y - 1500) / 600) ** 2))
    base += g2[..., None] * np.array([30, 60, 25], np.float32)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")

    # blurred stock board on the right
    board = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(board)
    f = rubik(120, "Bold")
    for row in range(9):
        yy = 60 + row * 150
        d.text((600, yy), "1,000", font=f, fill=(40, 170, 140, 110))
        d.text((985, yy), "3" + "5791"[row % 4], font=f, fill=(210, 40, 50, 120))
    board = board.filter(ImageFilter.GaussianBlur(9))
    fade = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 - v)  # strong at top
    board.putalpha(Image.fromarray(np.minimum(np.array(board.getchannel("A")), np.array(fade))))
    img.alpha_composite(board)
    return img


def card(path, h, radius=18):
    p = Image.open(path).convert("RGB")
    p = p.resize((int(p.width * h / p.height), h), Image.LANCZOS)
    m = Image.new("L", p.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, p.width - 1, p.height - 1), radius, fill=255)
    out = p.convert("RGBA")
    out.putalpha(m)
    return out


def shadowed(layer, blur=22, alpha=0.6, dy=18):
    pad = blur * 3
    out = Image.new("RGBA", (layer.width + 2 * pad, layer.height + 2 * pad + dy), (0, 0, 0, 0))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 255))
    sh.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    out.alpha_composite(sh, (pad, pad + dy))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(layer, (pad, pad))
    return out, pad


def paste_center(img, layer, cx, top, rot=0):
    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, expand=True)
    s, pad = shadowed(layer)
    img.alpha_composite(s, (int(cx - s.width / 2), int(top - pad)))


def person(name, height, dim=1.0, sharpen=True):
    p = Image.open(A / "characters" / f"{name}_cut.png").convert("RGBA")
    p = p.resize((int(p.width * height / p.height), height), Image.LANCZOS)
    if sharpen:
        rgb = p.convert("RGB").filter(ImageFilter.UnsharpMask(2, 80, 2))
        a = p.getchannel("A")
        p = rgb.convert("RGBA")
        p.putalpha(a)
    # soften the bottom edge so cropped torsos melt into the background
    fade = Image.linear_gradient("L").resize(p.size).point(lambda v: 255 if v < 150 else int(255 * (255 - v) / 105))
    p.putalpha(Image.fromarray(np.minimum(np.array(p.getchannel("A")), np.array(fade))))
    if dim != 1.0:
        a = p.getchannel("A")
        p = ImageEnhance.Brightness(p.convert("RGB")).enhance(dim).convert("RGBA")
        p.putalpha(a)
    return p


def bottom_fade(img, start, colour=(8, 10, 9)):
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(255 * max(0, min(1, (y - start) / (H - start))) ** 1.4))
    layer = Image.new("RGBA", (W, H), colour + (255,))
    layer.putalpha(grad.resize((W, H)))
    img.alpha_composite(layer)


def rtl_text(img, s, f, cx, cy, fill, shadow=True):
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    b = tmp.textbbox((0, 0), s, font=f, direction="rtl", language="fa")
    w, h = b[2] - b[0], b[3] - b[1]
    layer = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((40 - b[0], 40 - b[1]), s, font=f, fill=fill, direction="rtl", language="fa")
    if shadow:
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 255))
        sh.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.8)))
        img.alpha_composite(sh, (int(cx - layer.width / 2), int(cy - layer.height / 2) + 8))
    img.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def slanted_bar(img, s, cy, angle=4.5):
    bw, bh = 1400, 150
    x = np.linspace(0, 1, bw, dtype=np.float32)[None, :, None]
    left, right = np.array([250, 110, 20], np.float32), np.array([200, 25, 40], np.float32)
    grad = (left * (1 - x) + right * x).repeat(bh, axis=0)
    bar = Image.fromarray(grad.astype(np.uint8)).convert("RGBA")
    rtl_text(bar, s, rubik(64, "Bold"), bw / 2, bh / 2, (255, 255, 255), shadow=False)
    bar = bar.rotate(angle, resample=Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", bar.size, (0, 0, 0, 255))
    sh.putalpha(bar.getchannel("A").filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.5)))
    img.alpha_composite(sh, (int(W / 2 - bar.width / 2), int(cy - bar.height / 2) + 14))
    img.alpha_composite(bar, (int(W / 2 - bar.width / 2), int(cy - bar.height / 2)))


def main(out):
    img = background()

    # symbolic object: a fan of three series posters, top left (like the street sign / arrows)
    for i, (p, cx, top, rot) in enumerate([("p2.jpg", 190, 150, 14), ("p4.jpg", 330, 110, 4),
                                           ("p3.jpg", 470, 150, -8)]):
        paste_center(img, card(A / "posters" / p, 470), cx, top, rot)

    # back row of characters, a little darker, then the hero in front
    for name, h, cx, top, dim in [("don_draper", 640, 150, 560, 0.8),
                                  ("logan_roy", 640, 330, 640, 0.85),
                                  ("bobby_axelrod", 700, 900, 470, 0.85)]:
        p = person(name, h, dim)
        s, pad = shadowed(p, 30, 0.7, 10)
        img.alpha_composite(s, (int(cx - s.width / 2), int(top - pad)))
    hero = person("harvey_specter", 1180)
    hero.putalpha(Image.open(A / "characters" / "harvey_specter_cut.png").getchannel("A").resize(hero.size, Image.LANCZOS))
    s, pad = shadowed(hero, 34, 0.8, 0)
    img.alpha_composite(s, (int(620 - s.width / 2), int(H - hero.height - pad + 30)))

    bottom_fade(img, 1250)

    rtl_text(img, "MBA نخون!", rubik(175), W / 2, 1390, (255, 255, 255))
    slanted_bar(img, "به جاش این ۷ سریال رو ببین.", 1545)

    img.convert("RGB").save(out, quality=95)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "renders" / "7-series-cover.jpg"))
