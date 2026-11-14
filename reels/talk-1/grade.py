"""Pro grade, applied per frame at source resolution (numpy, float):
subject/background separation (bg darker, cooler, less saturated), soft key light on the face,
filmic tone curve with highlight roll-off, warm skin, teal shadows, local contrast."""
import numpy as np
from PIL import Image, ImageFilter

FACE = (240, 285)           # source coords (480x852)


def _key_light(h, w):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.exp(-(((x - FACE[0]) / 170) ** 2 + ((y - FACE[1]) / 210) ** 2))


KEY = None


def filmic(x):
    """Contrast S-curve with a slightly lifted black and a soft shoulder."""
    x = np.clip(x, 0, 1) ** 1.04
    s = 0.5 + 0.5 * np.tanh((x - 0.5) * 2.4) / np.tanh(1.2)
    return 0.018 + 0.965 * s


def grade(rgb, person):
    """rgb: HxWx3 uint8, person: HxW float 0..1 -> uint8"""
    global KEY
    h, w, _ = rgb.shape
    if KEY is None or KEY.shape != (h, w):
        KEY = _key_light(h, w)
    x = rgb.astype(np.float32) / 255
    # white balance: neutralise a slight green/cool cast
    x *= np.array([1.0, 0.99, 0.995], np.float32)
    # exposure + key light on the face (subject only)
    x *= 1.10 + 0.18 * (KEY * person)[..., None]
    # background: darker, cooler, less saturated -> subject pops
    lum = (x * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    bgk = (1 - person)[..., None]
    x = x * (1 - 0.30 * bgk) + lum * (0.30 * bgk)            # desaturate bg
    x = x * (1 - 0.32 * bgk)                                   # darken bg
    x = x + bgk * np.array([-0.01, 0.0, 0.015], np.float32)   # cool bg
    # filmic curve
    x = filmic(x)
    # split tone: teal shadows, warm highlights
    lum = (x * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    sh, hi = np.clip(1 - lum * 2, 0, 1), np.clip(lum * 2 - 1, 0, 1)
    x = x + sh * np.array([-0.012, 0.004, 0.018], np.float32) + hi * np.array([0.012, 0.006, -0.01], np.float32)
    # subject vibrance (skin warmth)
    mean = x.mean(-1, keepdims=True)
    x = mean + (x - mean) * (1 + 0.04 * person[..., None])
    out = Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8))
    # local contrast ("clarity")
    out = out.filter(ImageFilter.UnsharpMask(radius=14, percent=22, threshold=2))
    return np.array(out)
