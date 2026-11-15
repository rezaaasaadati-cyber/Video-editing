"""AI super-resolution (Real-ESRGAN general-x4v3 via spandrel, CPU, result scaled to 2x) for the frames the 30s cut actually uses,
then the same background blur + v2 grade as prep.py. Writes work/prep_hq_<clip>.mp4 (960x1704):
frames inside the EDL are upscaled, the rest are black (never shown)."""
import json, subprocess, sys, time
import numpy as np
import torch
from PIL import Image, ImageFilter
from spandrel import ModelLoader

torch.set_num_threads(4)
model = ModelLoader().load_from_file("work/models/realesr-general-x4v3.pth").model.eval()
Y0, Y1 = 40, 760            # rows that hold the speaker; the rest is blurred background anyway
E = json.load(open("work/edl30.json"))
W, H, PW, PH = 480, 852, 960, 1704
GRADE = ("hqdn3d=1:1:2:2,eq=contrast=1.08:brightness=0.03:saturation=1.12:gamma=1.04,"
         "colorbalance=rs=0.03:bs=-0.03:rm=0.02:bm=-0.02,curves=all='0/0 0.25/0.22 0.75/0.8 1/1',"
         "unsharp=3:3:0.35,vignette=PI/5")


def sr(rgb):
    base = np.array(Image.fromarray(rgb).resize((PW, PH), Image.LANCZOS))
    x = torch.from_numpy(np.ascontiguousarray(rgb[Y0:Y1])).permute(2, 0, 1).float().unsqueeze(0) / 255
    with torch.no_grad():
        y = model(x).clamp(0, 1)
    up = Image.fromarray((y[0].permute(1, 2, 0).numpy() * 255).round().astype(np.uint8))
    up = np.array(up.resize((PW, (Y1 - Y0) * 2), Image.LANCZOS))
    base[Y0 * 2:Y1 * 2] = up
    return base


for c in sys.argv[1:]:
    src = {"a": "raw/clip-a_173536.mp4", "b": "raw/clip-b_173633.mp4"}[c]
    ranges = [(s["in"] - 0.15, s["out"] + 0.8 if s is E[-1] else s["out"] + 0.15) for s in E if s["clip"] == c]
    use = lambda n: any(a <= n / 30 <= b for a, b in ranges)
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    msk = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", f"work/mask_{c}.mkv", "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    # one encoder applies the grade; frames the cut never shows are written black (cheap, never seen)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{PW}x{PH}",
                            "-r", "30", "-i", "-", "-vf", GRADE, "-c:v", "libx264", "-preset", "slow", "-crf", "10",
                            "-pix_fmt", "yuv420p", f"work/prep_hq_{c}.mp4"], stdin=subprocess.PIPE)
    BLACK = bytes(PW * PH * 3)
    yramp = np.clip((np.arange(PH)[:, None] / PH - 0.70) / 0.06, 0, 1)
    n, t0, done = 0, time.time(), 0
    while True:
        b = dec.stdout.read(W * H * 3); mk = msk.stdout.read(W * H)
        if len(b) < W * H * 3 or len(mk) < W * H:
            break
        if use(n):
            up = sr(np.frombuffer(b, np.uint8).reshape(H, W, 3))
            fr = Image.fromarray(up)
            m = Image.frombytes("L", (W, H), mk).resize((PW, PH), Image.BILINEAR)
            a = np.maximum(np.array(m) / 255.0, yramp)
            a = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))
            out = Image.composite(fr, fr.filter(ImageFilter.GaussianBlur(10)), a)
            enc.stdin.write(out.tobytes())
            done += 1
            if done % 50 == 0:
                print(c, n, f"{(time.time() - t0) / done:.2f}s/frame", flush=True)
        else:
            enc.stdin.write(BLACK)
        n += 1
    enc.stdin.close(); enc.wait()
    print(c, "frames", n, "upscaled", done, flush=True)
