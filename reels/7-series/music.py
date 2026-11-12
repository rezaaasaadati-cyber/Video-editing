"""Original phonk-style beat + sound design, synced to the reel's timeline (no samples, no
copyrighted audio: everything is synthesised here).

150 BPM, one beat = 12 video frames (0.4s), one bar = 1.6s.
  0.0 - 1.6   hook: a kick on every word cut, riser into the drop
  1.6 - 12.8  7 bars, one per series: kick/clap/hats, 808, cowbell melody, whoosh on each cut
  12.8 - 14.4 save card: half-time, click on the tap (14.0s) and a confirm chime
  14.4 - 16.4 logo: impact + sub boom, sparkle on the light sweep, tail

Usage: python3 music.py [out.wav]
"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
BPM = 150
BEAT = 60 / BPM            # 0.4s
BAR = 4 * BEAT
HOOK_END = BAR             # 1.6
SERIES_END = HOOK_END + 7 * BAR   # 12.8
SAVE_END = SERIES_END + BAR        # 14.4
TAP = SERIES_END + 3 * BEAT        # 14.0
TOTAL = SAVE_END + 2.0             # 16.4
N = int(TOTAL * SR)
rng = np.random.default_rng(7)


def t_arr(dur):
    return np.arange(int(dur * SR)) / SR


def env(dur, attack=0.002, decay=0.2):
    t = t_arr(dur)
    return np.minimum(1, t / attack) * np.exp(-t / decay)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "highpass", fs=SR, output="sos"), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "lowpass", fs=SR, output="sos"), x)


def add(bus, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= len(bus):
        return
    j = min(len(bus), i + len(sig))
    bus[i:j] += sig[: j - i] * gain


def note_hz(semitones_from_a4):
    return 440 * 2 ** (semitones_from_a4 / 12)


# ---------- instruments ----------
def kick(punch=1.0):
    d = 0.45
    t = t_arr(d)
    f = 45 + 110 * np.exp(-t / 0.03)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * env(d, 0.001, 0.16)
    click = hp(rng.standard_normal(len(t)), 2500) * env(d, 0.0005, 0.004) * 0.5
    return np.tanh((body + click) * 1.8 * punch)


def clap():
    d = 0.35
    n = rng.standard_normal(int(d * SR))
    e = np.zeros_like(n)
    for k, off in enumerate([0, 0.011, 0.022]):
        e += np.roll(env(d, 0.0005, 0.012 if k < 2 else 0.12), int(off * SR))
    return bp(n, 900, 5000) * e * 0.9


def hat(open_=False):
    d = 0.25 if open_ else 0.06
    n = rng.standard_normal(int(d * SR))
    return hp(n, 7000) * env(d, 0.0005, 0.08 if open_ else 0.015) * 0.35


def bass808(hz, d=0.7, glide_from=None):
    t = t_arr(d)
    f = np.full_like(t, hz)
    if glide_from:
        f = hz + (glide_from - hz) * np.exp(-t / 0.06)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * env(d, 0.003, 0.45)
    return np.tanh(s * 2.2) * 0.75


def cowbell(hz, d=0.18):
    t = t_arr(d)
    sq = lambda f: np.sign(np.sin(2 * np.pi * f * t))
    s = (sq(hz) + sq(hz * 1.48)) * 0.5
    return bp(s, 500, 3500) * env(d, 0.001, 0.07) * 0.32


def whoosh(d=0.35, up=True):
    n = rng.standard_normal(int(d * SR))
    t = t_arr(d)
    # sweep a band through the noise by crossfading three bands
    lo, mid, hi = bp(n, 300, 900), bp(n, 900, 3000), bp(n, 3000, 9000)
    x = t / d if up else 1 - t / d
    s = lo * (1 - x) + mid * (1 - abs(x - 0.5) * 2) + hi * x
    shape = np.sin(np.pi * t / d) ** 2
    return s * shape * 0.28


def riser(d):
    t = t_arr(d)
    n = rng.standard_normal(len(t))
    s = hp(n, 1500) * (t / d) ** 2.2 * 0.22
    tone = np.sin(2 * np.pi * np.cumsum(200 + 900 * (t / d) ** 2) / SR) * (t / d) ** 3 * 0.12
    return s + tone


def impact():
    d = 1.6
    t = t_arr(d)
    sub = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t / 0.08)) / SR) * env(d, 0.002, 0.6)
    noise = lp(rng.standard_normal(len(t)), 2500) * env(d, 0.001, 0.12) * 0.6
    return np.tanh((sub + noise) * 1.6) * 0.9


def click():
    d = 0.05
    t = t_arr(d)
    return (np.sin(2 * np.pi * 2200 * t) * env(d, 0.0003, 0.006)
            + hp(rng.standard_normal(len(t)), 3000) * env(d, 0.0003, 0.003) * 0.4) * 0.5


def chime(hz):
    d = 0.9
    t = t_arr(d)
    s = sum(np.sin(2 * np.pi * hz * m * t) * a for m, a in [(1, 1), (2, 0.4), (3, 0.15)])
    return s * env(d, 0.002, 0.25) * 0.18


def sparkle():
    d = 0.7
    out = np.zeros(int(d * SR))
    for k in range(9):
        hz = note_hz(24 + [0, 3, 7, 10, 12, 15, 19, 22, 24][k])
        add(out, chime(hz)[: int(0.4 * SR)] * 0.5, k * 0.045)
    return out


def reverb(x, seconds=1.4, mix=0.25):
    ir_t = t_arr(seconds)
    ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t / (seconds / 5))
    ir = lp(ir, 6000)
    ir /= np.sqrt(np.sum(ir ** 2))
    n = len(x) + len(ir)
    wet = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)]
    return x * (1 - mix) + wet * mix * 0.6


# ---------- arrangement ----------
def build():
    drums = np.zeros(N)
    bass = np.zeros(N)
    melody = np.zeros(N)
    fx = np.zeros(N)

    # hook: hit on each word cut, rising tension
    for b in range(4):
        add(drums, kick(0.9 + 0.1 * b), b * BEAT, 0.9)
        add(fx, whoosh(0.18, True), b * BEAT, 0.6)
    add(bass, bass808(note_hz(-30), 0.5), 0, 0.8)           # A1-ish thump on frame 0
    add(fx, riser(HOOK_END - 0.2), 0.2, 1.0)
    for k in range(8):                                          # snare roll into the drop
        add(drums, clap(), HOOK_END - BEAT * 2 + k * BEAT / 4, 0.25 + 0.06 * k)

    # main loop: one bar per series
    # cowbell riff in F# minor (semitones from A4), 16th grid, None = rest
    riff = [-3, None, -3, 0, None, -3, 2, None, 3, None, 2, 0, None, -3, -5, None]
    riff_b = [-3, None, -3, 0, None, -3, 2, None, 5, None, 3, 2, None, 0, -3, None]
    bass_notes = [-27, -27, -25, -22]                          # F#1 F#1 G#1 B1 by beat
    for bar in range(7):
        t0 = HOOK_END + bar * BAR
        add(fx, whoosh(0.32, True), t0 - 0.22, 0.9)           # whoosh lands on the cut
        add(drums, kick(1.1), t0, 1.0)
        add(drums, kick(), t0 + 2.5 * BEAT, 0.85)
        add(drums, kick(), t0 + 3 * BEAT, 0.7)
        add(drums, clap(), t0 + BEAT, 0.8)
        add(drums, clap(), t0 + 3 * BEAT, 0.8)
        for e in range(8):
            add(drums, hat(open_=(e == 7 and bar % 2 == 1)), t0 + e * BEAT / 2, 0.9)
        if bar % 2 == 1:                                       # trap hat roll at the end of the bar
            for r in range(6):
                add(drums, hat(), t0 + 3 * BEAT + BEAT / 2 + r * BEAT / 12, 0.6)
        add(bass, bass808(note_hz(bass_notes[0]), 0.9, glide_from=note_hz(bass_notes[0] + 7)), t0)
        add(bass, bass808(note_hz(bass_notes[2 if bar % 2 else 1]), 0.5), t0 + 2.5 * BEAT)
        r = riff_b if bar % 2 else riff
        for s, n in enumerate(r):
            if n is not None:
                add(melody, cowbell(note_hz(n + 12)), t0 + s * BEAT / 4)

    # save card: half-time, tap click + confirm chime
    t0 = SERIES_END
    add(fx, whoosh(0.32, True), t0 - 0.22, 0.9)
    add(drums, kick(), t0, 1.0)
    add(drums, clap(), t0 + 2 * BEAT, 0.8)
    for e in range(4):
        add(drums, hat(), t0 + e * BEAT, 0.6)
    add(bass, bass808(note_hz(-27), 1.2), t0, 0.9)
    for s, n in enumerate([-3, None, None, 0, None, None, 2, None]):
        if n is not None:
            add(melody, cowbell(note_hz(n + 12), 0.25), t0 + s * BEAT / 2, 0.8)
    add(fx, click(), TAP, 1.3)
    add(fx, chime(note_hz(15)), TAP + 0.05, 1.0)
    add(fx, chime(note_hz(22)), TAP + 0.15, 0.8)
    add(fx, riser(0.35), SAVE_END - 0.35, 0.8)

    # logo: impact on the mark, sparkle on the light sweep (outro frame 30 = +1.0s)
    add(fx, impact(), SAVE_END, 1.0)
    add(bass, bass808(note_hz(-27), 1.6, glide_from=note_hz(-15)), SAVE_END, 0.9)
    add(melody, cowbell(note_hz(9), 0.6), SAVE_END, 0.9)
    add(fx, whoosh(0.4, False), SAVE_END + 17 / 30, 0.6)     # wordmark slides out
    add(fx, sparkle(), SAVE_END + 1.0, 1.0)

    # mix
    bass = lp(bass, 400)
    melody = reverb(melody, 1.2, 0.3)
    fx = reverb(fx, 1.8, 0.25)
    # sidechain-ish duck of bass+melody under the kicks
    duck = np.ones(N)
    kick_times = [b * BEAT for b in range(4)]
    for bar in range(7):
        t0 = HOOK_END + bar * BAR
        kick_times += [t0, t0 + 2.5 * BEAT, t0 + 3 * BEAT]
    dk = 1 - 0.45 * env(0.25, 0.001, 0.08)
    for kt in kick_times:
        i = int(kt * SR)
        j = min(N, i + len(dk))
        duck[i:j] = np.minimum(duck[i:j], dk[: j - i])
    mix = drums * 0.9 + (bass * 0.9 + melody * 0.75) * duck + fx * 0.85
    # fade the tail, soft clip, normalise to -3 dBFS
    fade = int(0.35 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade) ** 2
    mix = np.tanh(mix * 1.2)
    mix *= 10 ** (-3 / 20) / np.max(np.abs(mix))
    # light stereo: hats/cowbell slightly wide via a tiny delay on the right
    right = np.concatenate([np.zeros(int(0.008 * SR)), mix])[:N] * 0.35 + mix * 0.65
    return np.stack([mix, right], axis=1)


def write_wav(path, stereo):
    import wave
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "assets" / "music.wav")
    write_wav(out, build())
    print(f"wrote {out}  ({TOTAL:.2f}s, {BPM} BPM)")
