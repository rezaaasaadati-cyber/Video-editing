#!/usr/bin/env python3
"""Build the lavashak peel reel (v3).

A/B peel montage at a relaxed cut rhythm, then the roll. No on-screen text.
Audio = the clips' own peel crackle, noise-stripped and EQ-matched to the reference
reel by clean_audio.py (run that first). No added SFX, no room noise.
"""
import subprocess, sys, os

U = "/root/.claude/uploads/5529e46e-a8aa-5e7f-bb60-b69d9b940427"
SRC = {
    "A": f"{U}/870b1ffb-20261111_114308.mp4",  # peel, wide
    "B": f"{U}/131ccd25-20261111_114411.mp4",  # peel, close
    "C": f"{U}/88a3cd6f-20261111_114739.mp4",  # rolling
}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/renders/lavashak-v5.mp4"

# (clip, in, out, speed)
EDL = [
    ("A", 1.60, 2.85, 1.0),   # hook: corner lifts off the plastic, loudest crackle
    ("B", 1.00, 2.25, 1.0),
    ("A", 2.85, 4.10, 1.0),
    ("B", 2.25, 3.50, 1.0),
    ("C", 7.30, 9.90, 1.0),   # payoff: rolled into a tube
]
# light: auto levels (keeps colour balance), gentle vibrance, B gets its shadows lifted
BASE = "normalize=blackpt=black:whitept=white:smoothing=20:independence=0:strength=0.6"
GRADE = {
    "A": f"{BASE},vibrance=intensity=0.10,eq=saturation=1.05",
    "B": f"{BASE},curves=master='0/0 0.25/0.30 0.5/0.57 1/1',vibrance=intensity=0.12,eq=saturation=1.06",
    "C": f"{BASE},vibrance=intensity=0.10,eq=saturation=1.05",
}
FPS = 30
GAIN = float(os.environ.get("GAIN", "37"))

inputs, vf, af, vl, al = [], [], [], [], []
t, starts = 0.0, []
n = len(EDL)
for i, (c, a, b, sp) in enumerate(EDL):
    inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", SRC[c]]
for i, (c, a, b, sp) in enumerate(EDL):
    inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", f"{HERE}/audio/{c}_clean.wav"]
for i, (c, a, b, sp) in enumerate(EDL):
    dur = (b - a) / sp
    starts.append((t, dur))
    # cute motion: springy "boing" zoom + jelly squash/stretch + a little wiggle on every cut
    def jelly(t0, amp, dec, hz):
        return f"(gte(t,{t0})*{amp}*exp(-(t-{t0})/{dec})*sin(2*PI*{hz}*(t-{t0})))"
    if c == "C":
        J = f"({jelly(0, 0.07, 0.16, 4.5)}+{jelly(1.90, 0.06, 0.18, 5)})"   # boing when the roll is finished
        Z = f"(1.10+0.08*exp(-t/0.14)*cos(2*PI*3*t)+0.06*t/{dur:.3f})"
        ROT = f"(0.022*{jelly(1.90, 1, 0.2, 3.5)})"
    else:
        J = jelly(0, 0.07, 0.16, 4.5)
        Z = f"(1.10+0.08*exp(-t/0.14)*cos(2*PI*3*t)+0.04*t/{dur:.3f})"
        side = 1 if i % 2 == 0 else -1
        ROT = f"({side}*0.026*exp(-t/0.22)*sin(2*PI*3.2*t))"
    SX, SY = f"({Z}*(1+{J}))", f"({Z}*(1-{J}))"
    vf.append(f"[{i}:v]setpts=(PTS-STARTPTS)/{sp},fps={FPS},scale=1080:1920:force_original_aspect_ratio=increase,"
              f"crop=1080:1920,{GRADE[c]},"
              f"scale=w='trunc(1080*{SX}/2)*2':h='trunc(1920*{SY}/2)*2':eval=frame:flags=bicubic,"
              f"rotate=a='{ROT}':ow=iw:oh=ih:c=black,"
              f"crop=1080:1920:x='(iw-1080)/2':y='(ih-1920)/2',"
              f"unsharp=5:5:0.5,setsar=1,format=yuv420p,trim=duration={dur:.4f}[v{i}]")
    tempo = f",atempo={sp}" if sp != 1.0 else ""
    af.append(f"[{n + i}:a]asetpts=PTS-STARTPTS{tempo},aformat=sample_rates=48000:channel_layouts=stereo,"
              f"atrim=duration={dur:.4f},afade=t=in:d=0.025,afade=t=out:st={dur - 0.03:.4f}:d=0.03[a{i}]")
    vl.append(f"[v{i}]"); al.append(f"[a{i}]")
    t += dur
TOTAL = t

fc = ";".join(vf + af)
fc += f";{''.join(vl)}concat=n={n}:v=1:a=0[vout]"
# soft sticky crackle bed under the roll (rolling itself is near-silent), from B's later peel
BED_START = [st for (st, _), e in zip(starts, EDL) if e[0] == "C"][0]
inputs += ["-ss", "3.6", "-t", "3.0", "-i", f"{HERE}/audio/B_clean.wav"]
bed = (f"[{2 * n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=-10dB,"
       f"afade=t=in:d=0.25,afade=t=out:st=2.0:d=0.6,adelay={int(BED_START * 1000)}:all=1[bed]")
fc += ";" + bed
# ASMR master: gentle dynamics, warm + crisp EQ, close-mic stereo with a slow left/right drift, tiny room
fc += (f";{''.join(al)}concat=n={n}:v=0:a=1[pk];[pk][bed]amix=inputs=2:normalize=0,"
       f"acompressor=threshold=-32dB:ratio=2.5:attack=3:release=90:makeup=1,"
       f"equalizer=f=350:t=q:w=1:g=3,equalizer=f=6000:t=q:w=1.2:g=2.5,highshelf=f=11000:g=2,"
       f"pan=mono|c0=c0,haas=level_in=1:level_out=1:side_gain=0.6:middle_source=mid:left_delay=0.4:right_delay=0.9,"
       f"apulsator=hz=0.22:amount=0.35:mode=sine,"
       f"aecho=0.85:0.6:13|21:0.10|0.06,"
       f"volume={GAIN}dB,aresample=192000,alimiter=limit=0.6:attack=1:release=40:level=0,lowpass=f=18000,"
       f"alimiter=limit=0.6:attack=0.5:release=20:level=0,"
       f"aresample=48000,atrim=duration={TOTAL:.4f}[aout]")

cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", OUT]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
subprocess.run(cmd, check=True)
print(f"OK {OUT} total={TOTAL:.2f}s cuts at", [round(s, 2) for s, _ in starts])
