"""30-second cut: explicit source pieces, each boundary snapped to the quietest 10 ms within +-0.12 s."""
import json, wave
import numpy as np

PIECES = [  # clip, in, out, sentence id, text spoken in this piece
    ("a", 0.00, 3.66, 0, "۲۱۷ نفر بهش گفتن نه"),
    ("a", 8.43, 9.44, 1, "هاوارد شولتز"),
    ("a", 10.46, 12.98, 1, "صاحب برند استارباکس"),
    ("a", 35.80, 40.10, 2, "این ایده به ذهنش رسید: کاری کنیم مردم رو از خونه بیاریم توی کافه"),
    ("b", 1.00, 4.15, 3, "سراغ ۲۴۲ نفر رفت"),
    ("b", 11.05, 14.52, 4, "بهش گفتن نه، نه، نه، نه"),
    ("b", 17.22, 19.02, 5, "۲۵ نفر"),
    ("b", 19.42, 21.65, 5, "بهش گفتن بیا تست بگیریم"),
    ("b", 38.90, 43.00, 6, "اول باید جسارت نه شنیدن رو داشته باشی"),
    ("b", 45.36, 45.80, 7, "امروز"),
    ("b", 48.36, 50.32, 7, "چند تا نه شنیدی؟"),
]


def rms(c):
    w = wave.open(f"work/audio_{c}.wav")
    x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
    hop = 160                                    # 10 ms at 16 kHz
    n = len(x) // hop
    return np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)


R = {c: rms(c) for c in "ab"}


def snap(c, t, win=0.12):
    r = R[c]
    i0, i1 = max(0, int((t - win) * 100)), min(len(r) - 1, int((t + win) * 100))
    if i1 <= i0:
        return t
    return (i0 + int(np.argmin(r[i0:i1 + 1]))) / 100


def build():
    out, acc = [], 0.0
    for c, a, b, sid, txt in PIECES:
        a2 = 0.0 if a == 0 else snap(c, a, 0.03 if txt.startswith("هاوارد") else 0.12)
        b2 = snap(c, b)
        out.append({"clip": c, "in": a2, "out": b2, "at": acc, "sid": sid, "text": txt})
        acc += b2 - a2
    return out, acc


if __name__ == "__main__":
    e, d = build()
    for s in e:
        print(s["clip"], f"{s['in']:.2f}-{s['out']:.2f}", f"@{s['at']:.2f}", s["text"])
    print("total", round(d, 2))
    json.dump(e, open("work/edl30.json", "w"), ensure_ascii=False, indent=1)
