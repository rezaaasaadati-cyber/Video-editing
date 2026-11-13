#!/usr/bin/env python3
"""Strip ambient noise from the clips' real peel crackle and EQ-match it to the reference reel.

In : audio/{A,B,C}_raw.wav (mono 48k from the originals), audio/ref.wav (reference reel)
Out: audio/{A,B,C}_clean.wav, work/eq_curve.png
"""
import numpy as np, soundfile as sf, noisereduce as nr, os
from scipy.signal import stft, istft, butter, sosfiltfilt
from scipy.ndimage import uniform_filter1d

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
SR = 48000
# quiet stretches (seconds) that contain only room noise, per clip
NOISE = {"A": [(0.0, 1.3), (5.2, 6.8)], "B": [(0.0, 0.5), (8.5, 10.0)], "C": [(4.6, 7.0)]}
# where the peel crackle is, used to measure our spectrum
PEEL = {"A": [(1.5, 4.5)], "B": [(1.0, 5.0)]}
REF_PEEL = (0.5, 5.5)


def seg(x, spans):
    return np.concatenate([x[int(a * SR):int(b * SR)] for a, b in spans])


def hp(x, f=250):
    return sosfiltfilt(butter(4, f, "highpass", fs=SR, output="sos"), x)


def avg_spec(x, n=2048):
    _, _, Z = stft(x, SR, nperseg=n)
    return np.sqrt(np.mean(np.abs(Z) ** 2, axis=1))


clean = {}
for c in "ABC":
    x, sr = sf.read(f"{D}/{c}_raw.wav"); assert sr == SR
    x = hp(x)  # room rumble / hum lives below ~250 Hz, the crackle does not
    noise = seg(x, NOISE[c])
    # two passes of stationary spectral gating against the clip's own room noise
    y = nr.reduce_noise(y=x, sr=SR, y_noise=noise, stationary=True, prop_decrease=1.0, n_std_thresh_stationary=1.8)
    y = nr.reduce_noise(y=y, sr=SR, y_noise=seg(y, NOISE[c]), stationary=True, prop_decrease=1.0,
                        n_std_thresh_stationary=1.5)
    clean[c] = y

# EQ match: our cleaned crackle -> reference crackle (smoothed, clamped)
ref, _ = sf.read(f"{D}/ref.wav")
ref = hp(ref)
r = avg_spec(ref[int(REF_PEEL[0] * SR):int(REF_PEEL[1] * SR)])
o = avg_spec(np.concatenate([seg(clean[c], PEEL[c]) for c in PEEL]))
freqs = np.linspace(0, SR / 2, len(r))
ratio_db = 20 * np.log10((r + 1e-9) / (o + 1e-9))
ratio_db -= np.median(ratio_db[(freqs > 1000) & (freqs < 8000)])  # shape only, level is set in the mix
ratio_db = uniform_filter1d(ratio_db, 25)
ratio_db = np.clip(ratio_db, -12, 9)
ratio_db[freqs < 250] = -24
gain = 10 ** (ratio_db / 20)

for c, y in clean.items():
    _, _, Z = stft(y, SR, nperseg=2048)
    Z *= gain[:, None]
    _, z = istft(Z, SR, nperseg=2048)
    z = z[:len(y)]
    z /= max(1e-9, np.max(np.abs(z))) / 0.9
    sf.write(f"{D}/{c}_clean.wav", z.astype(np.float32), SR)
    print(c, "peak-normalised, rms dBFS", round(20 * np.log10(np.sqrt(np.mean(z ** 2)) + 1e-12), 1))

try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    plt.figure(figsize=(8, 3)); plt.semilogx(freqs[1:], ratio_db[1:]); plt.xlim(100, 24000); plt.grid(True)
    plt.title("EQ applied to match reference"); plt.ylabel("dB"); plt.tight_layout()
    plt.savefig(os.path.join(os.path.dirname(D), "work", "eq_curve.png"))
except Exception as e:
    print("plot skipped:", e)
