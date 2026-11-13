#!/usr/bin/env python3
"""Build the lavashak peel reel: A/B peel montage with peel SFX, ending on the roll."""
import subprocess, sys, os

U = "/root/.claude/uploads/5529e46e-a8aa-5e7f-bb60-b69d9b940427"
SRC = {
    "A": f"{U}/870b1ffb-20261111_114308.mp4",  # peel, wide
    "B": f"{U}/131ccd25-20261111_114411.mp4",  # peel, close
    "C": f"{U}/88a3cd6f-20261111_114739.mp4",  # rolling
}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/renders/lavashak-v1.mp4"

# (clip, in, out, speed, sfx_offset, sfx_gain)
EDL = [
    ("A", 1.70, 2.30, 1.0, 1.40, 1.0),   # hook: corner lifts off the plastic
    ("B", 1.00, 1.50, 1.0, 1.50, 0.9),
    ("A", 2.30, 2.80, 1.0, 1.62, 1.0),
    ("B", 1.50, 2.00, 1.0, 1.38, 0.9),
    ("A", 2.80, 3.30, 1.0, 1.55, 1.0),
    ("B", 2.00, 2.50, 1.0, 1.45, 0.9),
    ("A", 3.30, 3.80, 1.0, 1.60, 1.0),
    ("B", 2.50, 3.00, 1.0, 1.42, 0.9),
    ("C", 7.30, 9.90, 1.15, 1.30, 0.35),    # payoff: rolled into a tube
]
GRADE = {
    "A": "eq=contrast=1.06:saturation=1.18",
    "B": "eq=contrast=1.08:saturation=1.15:gamma=1.18:brightness=0.03",
    "C": "eq=contrast=1.05:saturation=1.15",
}
FPS = 30

inputs, vf, af, vl, al = [], [], [], [], []
t = 0.0
starts = []
for i, (c, a, b, sp, so, sg) in enumerate(EDL):
    inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", SRC[c]]
    dur = (b - a) / sp
    starts.append((t, dur))
    v = (f"[{i}:v]setpts=(PTS-STARTPTS)/{sp},fps={FPS},scale=1080:1920:force_original_aspect_ratio=increase,"
         f"crop=1080:1920,{GRADE[c]},unsharp=5:5:0.6,setsar=1,format=yuv420p,"
         f"trim=duration={dur:.4f}[v{i}]")
    vf.append(v)
    # natural clip audio, quiet, tempo-matched
    tempo = f",atempo={sp}" if sp != 1.0 else ""
    af.append(f"[{i}:a]asetpts=PTS-STARTPTS{tempo},aresample=48000,aformat=channel_layouts=stereo,"
              f"volume=0.55,atrim=duration={dur:.4f},afade=t=in:d=0.01,afade=t=out:st={dur-0.015:.4f}:d=0.015[a{i}]")
    vl.append(f"[v{i}]"); al.append(f"[a{i}]")
    t += dur
TOTAL = t

n = len(EDL)
sfx_idx = n
inputs += ["-i", f"{HERE}/sfx/tape.mp3"]
# one peel SFX slice per peel cut, slightly varied pitch so repeats don't sound robotic
pitches = [1.0, 1.04, 0.97, 1.06, 0.99, 1.03, 0.96, 1.05, 0.85]
sfx_n = sum(1 for e in EDL if e[4] is not None)
splits = "".join(f"[s{k}]" for k in range(sfx_n))
mix = [f"[{sfx_idx}:a]aresample=48000,aformat=channel_layouts=stereo,asplit={sfx_n}{splits}"]
sl = []
k = 0
for i, (c, a, b, sp, so, sg) in enumerate(EDL):
    if so is None:
        continue
    st, dur = starts[i]
    p = pitches[k % len(pitches)]
    mix.append(f"[s{k}]atrim=start={so}:duration={dur + 0.05:.3f},asetpts=PTS-STARTPTS,"
               f"asetrate=48000*{p},aresample=48000,volume={sg * 1.8},"
               f"afade=t=in:d=0.02,afade=t=out:st={dur - 0.04:.3f}:d=0.08,"
               f"adelay={int(st * 1000)}|{int(st * 1000)}[x{k}]")
    sl.append(f"[x{k}]")
    k += 1

text_end = starts[-1][0]
ass = f"{HERE}/work/hook.ass"
with open(ass, "w", encoding="utf-8") as f:
    f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Big,Vazirmatn Black,150,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,9,4,8,60,60,330,1
Style: Small,Vazirmatn Black,88,&H0000E5FF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,3,8,60,60,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:{text_end:05.2f},Small,,0,0,0,,{{\\fad(0,120)}}با صدا ببین 🔊
Dialogue: 0,0:00:00.00,0:00:{text_end:05.2f},Big,,0,0,0,,{{\\fad(0,120)}}صدای کندن لواشک
""")

fc = ";".join(vf + af + mix)
fc += f";{''.join(vl)}concat=n={n}:v=1:a=0,ass={ass}:fontsdir={HERE}/fonts[vout]"
fc += f";{''.join(al)}concat=n={n}:v=0:a=1[nat]"
fc += f";[nat]{''.join(sl)}amix=inputs={1 + len(sl)}:normalize=0,alimiter=limit=0.7,"
fc += f"loudnorm=I=-18:TP=-3:LRA=11,volume=8dB,alimiter=limit=0.63:level=0,atrim=duration={TOTAL:.4f}[aout]"

cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", OUT]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
subprocess.run(cmd, check=True)
print(f"OK {OUT} total={TOTAL:.2f}s cuts at", [round(s, 2) for s, _ in starts])
