"""Studio-style voice track: same cuts as the edit (EDL from compose.py), then RNNoise denoise, low cut,
warmth, de-mud, presence, air, de-esser, two-stage compression, limiter, -14 LUFS. -> work/voice.wav"""
import importlib.util, subprocess
spec = importlib.util.spec_from_file_location("c", "compose.py"); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
parts = []
for k, seg in enumerate(c.EDL):
    i = "0" if seg["clip"] == "a" else "1"
    d = seg["out"] - seg["in"]
    parts.append(f"[{i}:a]atrim={seg['in']:.3f}:{seg['out']:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d=0.008,afade=t=out:st={d - 0.008:.3f}:d=0.008[s{k}]")
chain = (";".join(parts) + ";" + "".join(f"[s{k}]" for k in range(len(c.EDL))) +
         f"concat=n={len(c.EDL)}:v=0:a=1,pan=mono|c0=0.5*c0+0.5*c1,aresample=48000,"
         "arnndn=m=assets/audio/cb.rnnn:mix=0.85,"
         "highpass=f=85:poles=2,"
         "equalizer=f=130:t=o:w=1.0:g=2.0,"        # chest warmth
         "equalizer=f=320:t=q:w=1.4:g=-3.5,"       # boxiness / room
         "equalizer=f=900:t=q:w=1.2:g=-1.0,"
         "equalizer=f=3500:t=q:w=1.0:g=2.5,"       # presence
         "treble=g=2.5:f=10000,"                   # air
         "deesser=i=0.4:m=0.5:f=0.5,"
         "acompressor=threshold=-24dB:ratio=3.5:attack=5:release=80:makeup=3,"
         "acompressor=threshold=-14dB:ratio=2:attack=20:release=200:makeup=1,"
         "loudnorm=I=-15:TP=-2:LRA=7,alimiter=limit=0.85:level=false[out]")
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", "raw/clip-a_173536.mp4", "-i", "raw/clip-b_173633.mp4",
                "-filter_complex", chain, "-map", "[out]", "-ar", "48000", "work/voice_studio.wav"], check=True)
print("ok", round(c.DURATION, 2))
