"""30-second version of talk-1.

Reuses the machinery of compose.py (graphics, overlays, reader, ambient background) and changes:
- the edit: explicit pieces from edl30.py (work/edl30.json)
- the font: Doran FaNum everywhere
- the frame: the speaker alternates between the rounded card and FULL SCREEN, with an animated
  expand / shrink between the two
- captions aligned to Whisper words of the 30s voice track (work/words_out30.json)

Usage: python3 compose30.py [--stills 0,90] [--out renders/talk-1-30s-v1.mp4] [--audio work/mix30.wav]
"""
import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import compose as c  # noqa: E402

W, H, FPS = c.W, c.H, c.FPS
CREAM, NAVY_D, CYAN, ORANGE, RED, WHITE = c.CREAM, c.NAVY_D, c.CYAN, c.ORANGE, c.RED, c.WHITE
clamp, ease_out, ease_in_out, ease_back = c.clamp, c.ease_out, c.ease_in_out, c.ease_back

# ---------------- font: Doran FaNum everywhere ----------------
_F = {}
WEIGHT = {"ExtraBlack": "ExtraBold", "Heavy": "ExtraBold", "ExtraBold": "ExtraBold", "Bold": "Bold",
          "DemiBold": "Bold", "Medium": "Medium", "Regular": "Regular", "Light": "Light"}


def fnt(weight, size):
    key = (weight, size)
    if key not in _F:
        _F[key] = ImageFont.truetype(str(c.A / "fonts" / f"DoranFaNum-{WEIGHT[weight]}.ttf"), size)
    return _F[key]


c.fnt = fnt                      # every graphic / overlay in compose.py now uses Doran
c.SUB_F = fnt("ExtraBold", 62)

# ---------------- edit ----------------
EDL = json.load(open(ROOT / "work" / "edl30.json"))
DURATION = EDL[-1]["at"] + EDL[-1]["out"] - EDL[-1]["in"]
TOTAL = int(round(DURATION * FPS))
c.EDL, c.DURATION = EDL, DURATION


def to_out(clip, t):
    for s in EDL:
        if s["clip"] == clip and s["in"] - 1e-6 <= t <= s["out"] + 1e-6:
            return s["at"] + t - s["in"]
    raise ValueError((clip, t))


def seg_at(t):
    for k, s in enumerate(EDL):
        if s["at"] <= t < s["at"] + s["out"] - s["in"]:
            return k, s
    return len(EDL) - 1, EDL[-1]


# ---------------- captions ----------------
def _norm(w):
    return c._norm(w)


def build_words():
    toks = []
    for s in EDL:
        for w in s["text"].split():
            toks.append({"w": w, "clip": "x", "seg": s["sid"], "brk": w.endswith(("،", ":", "؟", ".", ","))})
    heard = json.load(open(ROOT / "work" / "words_out30.json"))
    a, b = [_norm(t["w"]) for t in toks], [_norm(w["w"]) for w in heard]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times = [None] * len(a)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k]["s"], heard[j1 + k]["e"])
        elif op == "replace":
            s0, e0 = heard[j1]["s"], heard[j2 - 1]["e"]
            lens = [max(1, len(a[i])) for i in range(i1, i2)]
            tot, acc = sum(lens), 0
            for i, L in zip(range(i1, i2), lens):
                times[i] = (s0 + (e0 - s0) * acc / tot, s0 + (e0 - s0) * (acc + L) / tot)
                acc += L
    for i in range(len(times)):
        if times[i] is None:
            prev = next((times[j][1] for j in range(i - 1, -1, -1) if times[j]), 0.0)
            nxt = next((times[j][0] for j in range(i + 1, len(times)) if times[j]), prev + 0.4)
            times[i] = (prev, max(prev + 0.08, min(nxt, prev + 0.4)))
    for t, (s_, e_) in zip(toks, times):
        t["s"], t["e"] = s_, max(e_, s_ + 0.08)
    return toks


WORDS = build_words()
c.WORDS = WORDS
CHUNKS = c.build_chunks(WORDS)


def word_t(token, sid):
    for w in WORDS:
        if w["seg"] == sid and token in w["w"]:
            return w["s"]
    raise KeyError(token)


# ---------------- moments ----------------
c.NAME_T = word_t("هاوارد", 1) - 0.1
c.SB_T = word_t("استارباکس", 1) - 0.05
IDEA_GFX = (to_out("a", 38.0), to_out("a", 40.22))


def gfx_idea(t, dur):
    cv = c.card_canvas()
    c.blur_in(cv, c.text_layer("ایدهٔ شولتز", fnt("ExtraBold", 92), ORANGE), c.CW / 2, 250, t)
    hx, sx, y = c.CW * .74, c.CW * .26, 560
    c.place(cv, c.icon_house(260, CREAM), hx, y, ease_back(t / .3))
    if t > .35:
        p = ease_out((t - .35) / .45)
        d = ImageDraw.Draw(cv)
        x1 = hx - 150 - (hx - sx - 300) * p
        d.line((hx - 150, y, x1, y), fill=CYAN, width=12)
        if p > .95:
            d.polygon([(x1 - 4, y), (x1 + 34, y - 26), (x1 + 34, y + 26)], fill=CYAN)
    if t > .75:
        c.place(cv, c.icon_store(260, CYAN), sx, y, ease_back((t - .75) / .3))
    c.blur_in(cv, c.text_layer("از خونه به کافه", fnt("ExtraBold", 70), CREAM), c.CW / 2, 830, t - 1.0)
    return cv


c.GFX["idea"] = gfx_idea

MOMENTS = [
    ("hook", 0.0, EDL[1]["at"]),
    ("name", c.NAME_T, EDL[3]["at"]),
    ("idea", *IDEA_GFX),
    ("count", EDL[4]["at"] + 0.05, EDL[5]["at"]),
    ("no", EDL[5]["at"], EDL[6]["at"]),
    ("yes", EDL[6]["at"], EDL[8]["at"]),
    ("keyword", word_t("جسارت", 6) - 0.05, EDL[9]["at"]),
    ("question", EDL[9]["at"], DURATION + 1),
]
CUTAWAYS = {"idea", "count", "no", "yes"}
HIDE_SUBS = {"hook", "question", "count", "no", "yes", "idea"}
SUB_LOW = {"name", "keyword"}
c.SUB_LOW = SUB_LOW
c.MOMENTS = MOMENTS
c.CUTAWAYS, c.HIDE_SUBS = CUTAWAYS, HIDE_SUBS


def ov_hook(img, t, dur, full):
    y0 = 1060 if full else 1110
    c.place(img, c.text_layer("۲۱۷ نفر", fnt("ExtraBold", 210), CREAM), W / 2, y0, 1.08 - .08 * ease_back(t / .25))
    if t > .55:
        c.place(img, c.pill("بهش گفتن «نه»", fnt("ExtraBold", 78), RED, WHITE), W / 2, y0 + 190,
                ease_back((t - .55) / .25), rot=-3)


def ov_question(img, t, dur, full):
    c.ov_question(img, t, dur)
    if t > 1.2:          # save / share nudge under the question
        c.blur_in(img, c.pill("کامنت کن: امروز چند تا؟", fnt("Bold", 46), CYAN, NAVY_D), W / 2, 1420, t - 1.2)


OVER = {"hook": ov_hook, "question": ov_question,
        "name": lambda img, t, d, f: c.ov_name(img, t, d),
        "keyword": lambda img, t, d, f: c.ov_keyword(img, t, d)}


def active(t):
    for name, s, e in MOMENTS:
        if s <= t < e:
            return name, t - s, e - s
    return None, 0, 0


# ---------------- card <-> full screen ----------------
# 1 = full screen. Hook, the idea line, "no, no, no" lead-in and the closing question go full.
FULL_SPANS = [(0.0, EDL[1]["at"]), (EDL[3]["at"], IDEA_GFX[0]), (EDL[8]["at"], EDL[9]["at"])]
TR = 0.28                      # transition length (s)


def fullness(t):
    v = 0.0
    for s, e in FULL_SPANS:
        if s - 1e-3 <= t < e:
            a = 1.0 if s <= 0 else ease_in_out((t - s) / TR)
            b = ease_in_out((e - t) / TR)
            v = max(v, min(a, b))
    return v


def rect(f):
    x0 = c.CX0 * (1 - f)
    y0 = c.CY0 * (1 - f)
    x1 = (c.CX0 + c.CW) * (1 - f) + W * f
    y1 = (c.CY0 + c.CH) * (1 - f) + H * f
    return int(x0), int(y0), int(x1), int(y1), int(c.RADIUS * (1 - f))


def speaker(fr, z, w, h, grey):
    """Crop the prepped frame to w x h around the face, zoom z."""
    scale = max(w / c.PW, h / c.PH) * z
    cw, ch = w / scale, h / scale
    fx, fy = c.FACE
    x0 = clamp(fx - cw / 2, 0, c.PW - cw)
    base_y = c.SRC_Y0 if h / w < 1.3 else max(0, fy - ch * 0.33)       # full screen: face at upper third
    y0 = clamp(fy - (fy - base_y) / z, 0, c.PH - ch)
    im = fr.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((w, h), Image.BICUBIC)
    if grey > 0:
        im = Image.blend(im, im.convert("L").convert("RGB"), grey)
    return im.convert("RGBA")


TOP_GRAD = Image.new("RGBA", (W, 420), NAVY_D + (0,))
TOP_GRAD.putalpha(Image.fromarray((np.linspace(170, 0, 420)[:, None].repeat(W, 1)).astype(np.uint8)))
BOT_GRAD = Image.new("RGBA", (W, 700), NAVY_D + (0,))
BOT_GRAD.putalpha(Image.fromarray((np.linspace(0, 190, 700)[:, None].repeat(W, 1)).astype(np.uint8)))
READER = c.Reader()


def render(n):
    t = n / FPS
    k, seg = seg_at(t)
    t_in = seg["in"] + (t - seg["at"])
    name, tl, dur = active(t)
    fr = READER.frame(k, seg, t_in)
    f = 0.0 if name in CUTAWAYS else fullness(t)

    img = c.ambient(fr)
    img.alpha_composite(c.OVERLAY if f < 0.5 else Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    x0, y0, x1, y1, rad = rect(f)
    w, h = x1 - x0, y1 - y0
    grey = 1 - clamp((t - 0.9) / 0.3) if t < 1.2 else 0.0
    z = c.zoom_for(t)
    if name in CUTAWAYS:
        card = c.GFX[name](tl, dur).resize((w, h))
        inn, out = ease_out(tl / .18), ease_out((dur - tl) / .18)
        if inn < 1 or out < 1:
            base = speaker(fr, z, w, h, 0)
            m = Image.new("L", (w, h), 0)
            ImageDraw.Draw(m).rectangle((w - int(w * min(inn, out)), 0, w, h), fill=255)
            base.paste(card, (0, 0), m)
            card = base
    else:
        card = speaker(fr, z, w, h, grey)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), max(0, rad), fill=255)
    img.paste(card, (x0, y0), mask)

    if f > 0.02:     # full screen: readable top for the logo, darker bottom for captions
        tg = TOP_GRAD.copy(); tg.putalpha(tg.getchannel("A").point(lambda v: int(v * f)))
        bg = BOT_GRAD.copy(); bg.putalpha(bg.getchannel("A").point(lambda v: int(v * f)))
        img.alpha_composite(tg, (0, 0)); img.alpha_composite(bg, (0, H - 700))
        img.alpha_composite(c.LOGO, (W // 2 - c.LOGO.width // 2, 278 - c.LOGO.height // 2))

    # progress line
    d = ImageDraw.Draw(img)
    py = 340
    d.rounded_rectangle((90, py, W - 90, py + 6), 3, fill=(255, 255, 255, 60))
    px = W - 90 - (W - 180) * (t / DURATION)
    d.rounded_rectangle((px, py, W - 90, py + 6), 3, fill=ORANGE)

    if name in OVER:
        OVER[name](img, tl, dur, f > 0.5)
    if name not in HIDE_SUBS:
        for ch in CHUNKS:
            if ch["s"] <= t < ch["e"]:
                cap = c.caption_layer(ch, t)
                pop = ease_back(min(1, (t - ch["s"]) / 0.12), 1.4)
                y = c.SUB_Y_LOW if name in SUB_LOW else c.SUB_Y
                c.place(img, cap, W / 2, y, 0.9 + 0.1 * pop)
                break
    return img.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills")
    ap.add_argument("--out", default=str(ROOT / "renders" / "talk-1-30s-v1.mp4"))
    ap.add_argument("--audio", default=str(ROOT / "work" / "mix30.wav"))
    a = ap.parse_args()
    if a.stills:
        for n in map(int, a.stills.split(",")):
            render(n).save(ROOT / "work" / f"s30_{n:04d}.png")
        return
    p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", a.audio, "-map", "0:v", "-map", "1:a", "-shortest",
                          "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                          "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", a.out], stdin=subprocess.PIPE)
    for n in range(TOTAL):
        p.stdin.write(render(n).tobytes())
    p.stdin.close()
    p.wait()
    print("wrote", a.out, f"{DURATION:.2f}s")


if __name__ == "__main__":
    main()
