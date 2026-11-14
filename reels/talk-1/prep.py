"""Per clip: portrait-mode background blur + pro grade (grade.py: subject/background separation, key light, filmic curve) (MediaPipe person mask, desk kept sharp), then colour grade,
denoise and 2x Lanczos upscale with sharpening -> work/prep_<c>.mp4 (960x1704, 30fps, video only).
Usage: python3 prep.py a raw/clip-a_173536.mp4
"""
import subprocess, sys
import numpy as np
from PIL import Image, ImageFilter

c, src = sys.argv[1], sys.argv[2]
W, H = 480, 852
GRADE = "hqdn3d=1.5:1.5:3:3,scale=960:1704:flags=lanczos,unsharp=5:5:0.6,vignette=PI/6"
import importlib.util
_s = importlib.util.spec_from_file_location("grade", "grade.py"); G = importlib.util.module_from_spec(_s); _s.loader.exec_module(G)
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
    out = G.grade(np.array(out), np.array(a).astype(np.float32) / 255)
    enc.stdin.write(out.tobytes())
    n += 1
enc.stdin.close(); enc.wait()
print(c, "frames", n)
