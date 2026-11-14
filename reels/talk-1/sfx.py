"""Sound effects synced to the edit's moments (all synthesised, no samples), mixed under the studio voice.
-> work/sfx.wav and work/mix.wav"""
import importlib.util, sys, wave
import numpy as np
sys.path.insert(0, "../7-series")
import music as m                                      # reuse the synth voices from the 7-series beat

spec = importlib.util.spec_from_file_location("c", "compose.py"); c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
SR = m.SR
N = int((c.DURATION + 1.0) * SR)
bus = np.zeros(N)
rng = np.random.default_rng(3)


def add(sig, t, g):
    m.add(bus, sig, t, g)


def pop(hz=900):
    t = m.t_arr(0.09)
    f = hz * (1 + 1.5 * np.exp(-t / 0.01))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * m.env(0.09, 0.001, 0.025) * 0.6


def tick():
    return m.click() * 0.6


def thud():
    return m.kick(0.8) * 0.8 + m.hp(rng.standard_normal(int(0.08 * SR)), 1500)[: int(0.08 * SR)].tolist() * 0 if False else m.kick(0.8) * 0.8


def buzz():
    t = m.t_arr(0.22)
    s = np.sign(np.sin(2 * np.pi * 110 * t)) * 0.5 + np.sign(np.sin(2 * np.pi * 116 * t)) * 0.5
    return m.lp(s, 1800) * m.env(0.22, 0.003, 0.09) * 0.35


M = {name: (s, e) for name, s, e in c.MOMENTS}

# hook
add(m.impact()[: int(1.0 * SR)], 0.0, 0.55)
add(thud(), M["hook"][0] + 0.5, 0.7); add(buzz(), M["hook"][0] + 0.5, 0.6)
add(m.whoosh(0.3), M["hook"][0] + 1.6, 0.6); add(pop(1100), M["hook"][0] + 1.72, 0.5)
# name card: pop for the photo, chime when the Starbucks logo lands
add(m.whoosh(0.35), M["name"][0] - 0.05, 0.6); add(pop(900), M["name"][0] + 0.05, 0.6)
add(m.chime(m.note_hz(15)), c.SB_T + 0.05, 0.9); add(pop(1200), c.SB_T, 0.5)
s, e = M["cafe"]; add(pop(1100), s + 0.05, 0.6); add(m.chime(m.note_hz(19)), s + 0.25, 0.6)
# cutaways: whoosh in and out
for k in ["home", "decade", "count", "no", "yes"]:
    s, e = M[k]
    add(m.whoosh(0.32, True), s - 0.12, 0.8)
    add(m.whoosh(0.28, False), e - 0.2, 0.55)
s, e = M["home"]; add(pop(700), s + 0.05, 0.6); add(pop(1200), s + 0.4, 0.6)
s, e = M["decade"]; add(pop(800), s + 0.05, 0.5); add(m.whoosh(0.45), s + 0.45, 0.5); add(pop(1000), s + 0.95, 0.6)
s, e = M["count"]
for k in range(40):                                     # ticks that slow down as the counter settles
    tt = 1.6 * (1 - (1 - k / 40) ** 0.5)
    add(tick(), s + tt, 0.35)
add(m.chime(m.note_hz(12)), s + 1.65, 0.7)
s, e = M["no"]
for k in range(30):
    add(tick(), s + 3.2 * (k / 30) ** 1.4, 0.25)
dur = e - s
for k in range(4):
    add(thud(), s + dur - 1.6 + 0.4 * k, 0.6); add(buzz(), s + dur - 1.6 + 0.4 * k, 0.5)
s, e = M["yes"]
for k, n in enumerate([0, 4, 7, 12]):
    add(m.chime(m.note_hz(12 + n)), s + 0.1 + k * 0.12, 0.7)
add(pop(1100), s + 1.6, 0.6)
# overlays
s, e = M["keyword"]; add(m.whoosh(0.3), s - 0.1, 0.6); add(thud(), s + 0.22, 0.45)
s, e = M["question"]; add(pop(900), s, 0.7); add(m.whoosh(0.3), s - 0.1, 0.5)
s, e = M["cta"]; add(pop(1000), s, 0.7); add(m.whoosh(0.6), s + 0.6, 0.7)
# soft swish on every sentence punch-in (very low)
last = None
for w in c.WORDS:
    key = (w["clip"], w["seg"])
    if key != last and w["s"] > 4:
        add(m.whoosh(0.18), w["s"] - 0.1, 0.18)
    last = key

bus = m.reverb(bus, 0.8, 0.12)
bus *= 10 ** (-9 / 20) / max(1e-9, np.abs(bus).max())          # SFX peak -9 dBFS, voice sits above

w = wave.open("work/voice_studio.wav"); v = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
if w.getnchannels() == 2:
    v = v.reshape(-1, 2).mean(1)
mix = np.zeros(max(len(v), N)); mix[: len(v)] += v
# duck SFX slightly under speech energy
env = np.convolve(np.abs(mix), np.ones(2400) / 2400, mode="same")
duck = 1 - 0.35 * np.clip(env / (env.max() * 0.3), 0, 1)
mix += bus[: len(mix)] * duck[: len(bus)] if len(bus) >= len(mix) else 0
mix = mix[: len(v)]
mix *= min(1.0, 10 ** (-1.5 / 20) / np.abs(mix).max())
for name, sig in [("work/sfx.wav", bus), ("work/mix.wav", mix)]:
    out = wave.open(name, "wb"); out.setnchannels(1); out.setsampwidth(2); out.setframerate(SR)
    out.writeframes((np.clip(sig, -1, 1) * 32767).astype("<i2").tobytes()); out.close()
print("ok", len(mix) / SR)
