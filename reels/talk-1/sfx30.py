"""SFX for the 30s cut, mixed under work/voice30.wav -> work/mix30.wav"""
import sys, wave
import numpy as np
sys.path.insert(0, "../7-series"); sys.path.insert(0, ".")
import music as m
import compose30 as k

SR = m.SR
N = int((k.DURATION + k.OUTRO + 1) * SR)
bus = np.zeros(N)


def add(sig, t, g):
    m.add(bus, sig, max(0.0, t), g)


def pop(hz=900):
    t = m.t_arr(0.09)
    f = hz * (1 + 1.5 * np.exp(-t / 0.01))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * m.env(0.09, 0.001, 0.025) * 0.6


M = {n: (s, e) for n, s, e in k.MOMENTS}
add(pop(800), M["hook"][0] + 0.55, 0.5)
add(m.whoosh(0.35), M["name"][0] - 0.05, 0.6); add(pop(900), M["name"][0] + 0.05, 0.6)
add(m.chime(m.note_hz(15)), k.c.SB_T + 0.05, 0.9); add(pop(1200), k.c.SB_T, 0.5)
for n in ["idea", "count", "no", "yes"]:
    s, e = M[n]
    add(m.whoosh(0.32, True), s - 0.12, 0.8); add(m.whoosh(0.28, False), e - 0.2, 0.5)
s, e = M["idea"]; add(pop(800), s + 0.05, 0.5); add(m.whoosh(0.45), s + 0.35, 0.5); add(pop(1000), s + 0.8, 0.6)
s, e = M["count"]
for i in range(40):
    add(m.click() * 0.6, s + 1.6 * (1 - (1 - i / 40) ** 0.5), 0.35)
add(m.chime(m.note_hz(12)), s + 1.65, 0.7)
s, e = M["no"]
for i in range(30):
    add(m.click() * 0.6, s + 3.2 * (i / 30) ** 1.4, 0.25)
for i in range(4):
    add(m.kick(0.8) * 0.8, s + (e - s) - 1.6 + 0.4 * i, 0.5)
s, e = M["yes"]
for i, n in enumerate([0, 4, 7, 12]):
    add(m.chime(m.note_hz(12 + n)), s + 0.1 + i * 0.12, 0.7)
s, e = M["keyword"]; add(m.whoosh(0.3), s - 0.1, 0.6); add(m.kick(0.8) * 0.8, s + 0.22, 0.4)
s, e = M["question"]; add(pop(900), s, 0.7); add(m.whoosh(0.3), s - 0.1, 0.5)
for s_, e_ in k.FULL_SPANS[1:]:                      # expand / shrink of the frame
    add(m.whoosh(0.3), s_ - 0.1, 0.45); add(m.whoosh(0.3, False), e_ - 0.2, 0.35)

# closing sting on the end card: soft low hit + resolved chord, so it clearly ends
D = k.DURATION
add(m.whoosh(0.4, True), D - 0.15, 0.6)
add(m.kick(0.6) * 0.7, D + 0.3, 0.5)
for i, n in enumerate([0, 7, 12, 16, 19]):
    add(m.chime(m.note_hz(3 + n)), D + 0.3 + i * 0.03, 0.75)

bus = m.reverb(bus, 1.4, 0.2)
bus *= 10 ** (-9 / 20) / max(1e-9, np.abs(bus).max())
w = wave.open("work/voice30.wav"); v = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
L = int((k.DURATION + k.OUTRO) * SR)
mix = np.zeros(L); mix[: min(L, len(v))] += v[:L]
env = np.convolve(np.abs(mix), np.ones(2400) / 2400, mode="same")
duck = 1 - 0.35 * np.clip(env / (env.max() * 0.3), 0, 1)
mix += bus[: len(mix)] * duck[: len(mix)] if len(bus) >= len(mix) else 0
fade = int(0.5 * SR); mix[-fade:] *= np.linspace(1, 0, fade) ** 1.5
mix *= min(1.0, 10 ** (-1.5 / 20) / np.abs(mix).max())
o = wave.open("work/mix30_raw.wav", "wb"); o.setnchannels(1); o.setsampwidth(2); o.setframerate(SR)
o.writeframes((np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes()); o.close()
print("ok", len(mix) / SR)
