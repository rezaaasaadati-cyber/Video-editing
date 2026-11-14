"""Per clip: portrait-mode background blur (MediaPipe person mask, desk kept sharp), then colour grade,
denoise and 2x Lanczos upscale with sharpening -> work/prep_<c>.mp4 (960x1704, 30fps, video only).
Usage: python3 prep.py a raw/clip-a_173536.mp4
"""
import subprocess, sys
import numpy as np
from PIL import Image, ImageFilter

c, src = sys.argv[1], sys.argv[2]
W, H = 480, 852
GRADE = ("hqdn3d=2:2:3:3,eq=contrast=1.08:brightness=0.03:saturation=1.12:gamma=1.04,"
         "colorbalance=rs=0.03:bs=-0.03:rm=0.02:bm=-0.02,curves=all='0/0 0.25/0.22 0.75/0.8 1/1',"
         "scale=960:1704:flags=lanczos,unsharp=5:5:0.8,vignette=PI/5")
dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       stdout=subprocess.PIPE)
msk = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", f"work/mask_{c}.mkv", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                        "-r", "30", "-i", "-", "-vf", GRADE, "-c:v", "libx264", "-preset", "slow", "-crf", "12",
                        "-pix_fmt", "yuv420p", f"work/prep_{c}.mp4"], stdin=subprocess.PIPE)
yramp = np.clip((np.arange(H)[:, None] / H - 0.70) / 0.06, 0, 1)   # keep the desk sharp
n = 0
while True:
    b = dec.stdout.read(W * H * 3)
    m = msk.stdout.read(W * H)
    if len(b) < W * H * 3 or len(m) < W * H:
        break
    fr = Image.frombytes("RGB", (W, H), b)
    a = np.maximum(np.frombuffer(m, np.uint8).reshape(H, W) / 255.0, yramp)
    a = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
    out = Image.composite(fr, fr.filter(ImageFilter.GaussianBlur(5)), a)
    enc.stdin.write(out.tobytes())
    n += 1
enc.stdin.close(); enc.wait()
print(c, "frames", n)
