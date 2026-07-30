#!/usr/bin/env python3
"""Generate original music beds for the Instagram reels.

WHY THIS EXISTS. A reel needs audio and Departs Daily is a commercial site, so
the options were: pay a library, use Meta's Sound Collection (free, but cleared
for Meta platforms only and it has to be pulled by hand from a logged-in
account), or own the music outright. This is the third. Every track here is
synthesised from scratch, so there is no licence, no attribution, no Content ID
risk, and no third party who can change their terms later.

It also means the tracks can be regenerated and tweaked. Change the tempo,
change the progression, re-run, and the reels have new music.

Everything is written to be SHORT-FORM FIRST: the hook lands in the first bar,
because a reel is 10 to 13 seconds and a track that spends 20 seconds building
up is useless to us.

Usage:
    python3 scripts/make_reel_music.py            # all tracks -> assets/reel-audio/
    python3 scripts/make_reel_music.py runway     # just one
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

SR = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "reel-audio")


def midi(n):
    return 440.0 * 2.0 ** ((n - 69) / 12.0)


def env(n, a, d, s, r, sus=0.7):
    """Straight ADSR in samples-from-seconds. Kept explicit rather than clever
    because every instrument below wants a different shape."""
    a, d, r = max(1, int(a * SR)), max(1, int(d * SR)), max(1, int(r * SR))
    s = max(0, n - a - d - r)
    return np.concatenate([
        np.linspace(0, 1, a),
        np.linspace(1, sus, d),
        np.full(s, sus),
        np.linspace(sus, 0, r),
    ])[:n]


def saw(freq, n, detune=0.0):
    """Additive sawtooth. Band-limited by construction — no aliasing, which is
    what makes a naive np.mod() saw sound like a fax machine."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    voices = [1.0] if detune == 0 else [1.0 - detune, 1.0, 1.0 + detune]
    for v in voices:
        f = freq * v
        for h in range(1, int(SR / 2 / f) + 1):
            if h > 26:
                break
            out += np.sin(2 * np.pi * f * h * t) / h
    return out / len(voices) * 0.5


def square(freq, n, duty=0.5):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for h in range(1, 20, 2):
        if freq * h > SR / 2:
            break
        out += np.sin(2 * np.pi * freq * h * t) / h
    return out * 0.5


def sine(freq, n):
    return np.sin(2 * np.pi * freq * np.arange(n) / SR)


def lowpass(x, cutoff, res=1.0):
    """One-pole per stage, two stages. Cheap, and on a mix this dense the
    difference between this and a proper biquad is not audible."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    z1 = z2 = 0.0
    for i in range(len(x)):
        z1 = (1 - a) * x[i] + a * z1
        z2 = (1 - a) * z1 + a * z2
        y[i] = z2
    return y * res


def lowpass_fft(x, cutoff):
    """FFT version — the sample-loop above is far too slow for a full track."""
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    spec *= 1.0 / (1.0 + (freqs / max(cutoff, 1.0)) ** 4)
    return np.fft.irfft(spec, n)


def highpass_fft(x, cutoff):
    n = len(x)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    r = (freqs / max(cutoff, 1.0)) ** 4
    spec *= r / (1.0 + r)
    return np.fft.irfft(spec, n)


def place(buf, sig, at):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[:j - i]


# ------------------------------------------------------------------ drums


def kick(n=None):
    n = n or int(0.34 * SR)
    t = np.arange(n) / SR
    # Pitch sweep is what makes a kick read as a kick: 130Hz down to 45Hz fast.
    f = 45 + 95 * np.exp(-t * 32)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8.5)
    click = np.random.RandomState(1).randn(n) * np.exp(-t * 420) * 0.28
    return np.tanh((body + click) * 1.7) * 0.92


def clap(n=None):
    n = n or int(0.26 * SR)
    t = np.arange(n) / SR
    rs = np.random.RandomState(7)
    out = np.zeros(n)
    # Three fast bursts, then the tail. That stagger is the difference between
    # a clap and a noise blip.
    for k, off in enumerate((0.0, 0.011, 0.022)):
        s = int(off * SR)
        seg = rs.randn(n - s) * np.exp(-np.arange(n - s) / SR * 190)
        out[s:] += seg * (0.85 ** k)
    out += rs.randn(n) * np.exp(-t * 22) * 0.4
    return highpass_fft(out, 900) * 0.5


def hat(dur=0.055, open_=False):
    n = int(dur * SR)
    t = np.arange(n) / SR
    rs = np.random.RandomState(3)
    d = 55 if open_ else 190
    # Band-limited both ends. A pure highpassed noise hat puts a quarter of the
    # track's energy above 8kHz, which reads as hiss under spoken-word-free
    # video and fatigues fast on phone speakers.
    h = highpass_fft(rs.randn(n) * np.exp(-t * d), 6200)
    return lowpass_fft(h, 11000) * 0.24


# ------------------------------------------------------------------ track


def build(name, bpm, root, prog, bars=11, mood="bright", arp_pattern=None):
    """One finished track. `prog` is a list of (semitone offset from root,
    chord quality) per bar, cycling."""
    spb = 60.0 / bpm            # seconds per beat
    bar = spb * 4
    total = bar * bars
    n = int(total * SR) + SR
    mix = np.zeros(n)
    bass_bus = np.zeros(n)
    lead_bus = np.zeros(n)
    pad_bus = np.zeros(n)

    QUAL = {"min": (0, 3, 7, 10), "maj": (0, 4, 7, 11), "sus": (0, 5, 7, 10)}

    # A one bar count-in of hats only, so the drop lands on bar 2 and the first
    # second of the reel is not silence.
    for b in range(bars):
        t0 = b * bar
        deg, qual = prog[b % len(prog)]
        chord = [root + deg + i for i in QUAL[qual]]

        # --- drums
        if b >= 1:
            for beat in range(4):
                place(mix, kick() * 0.95, t0 + beat * spb)
            for beat in (1, 3):
                place(mix, clap() * 0.62, t0 + beat * spb)
        for eighth in range(8):
            if b == 0 and eighth < 4:
                continue
            op = eighth == 7
            place(mix, hat(0.13 if op else 0.05, op) * (0.5 if op else 0.32),
                  t0 + eighth * spb / 2)

        # --- bass: root on every eighth, octave down, plucky
        if b >= 1:
            for eighth in range(8):
                if eighth in (3, 6):
                    continue
                ln = int(spb / 2 * 0.92 * SR)
                f = midi(chord[0] - 24)
                sig = (saw(f, ln, 0.004) * 0.6 + sine(f, ln) * 0.75)
                sig *= env(ln, 0.004, 0.05, 0, 0.05, sus=0.55)
                place(bass_bus, sig, t0 + eighth * spb / 2)

        # --- pad: the chord, soft, underneath everything
        pl = int(bar * 0.98 * SR)
        pad = np.zeros(pl)
        for note in chord[:3]:
            pad += saw(midi(note), pl, 0.006) * 0.3
        pad *= env(pl, 0.12, 0.2, 0, 0.5, sus=0.55)
        place(pad_bus, pad, t0)

        # --- lead arp: the hook. Sixteenths through the chord with octave
        # jumps and deliberate rests, so it has a rhythm instead of a run.
        pat = arp_pattern or [0, 1, 2, 1, 3, 2, 1, 0, 2, 3, 4, 3, 2, 1, 0, 1]
        notes = chord + [chord[0] + 12, chord[1] + 12]
        for s16 in range(16):
            if b == 0:
                break
            slot = pat[s16 % len(pat)]
            if slot is None:
                continue
            ln = int(spb / 4 * 1.5 * SR)
            f = midi(notes[slot % len(notes)] + 12)
            sig = square(f, ln, 0.35) * 0.5 + saw(f, ln, 0.008) * 0.5
            sig *= env(ln, 0.002, 0.04, 0, 0.09, sus=0.28)
            place(lead_bus, sig * 0.5, t0 + s16 * spb / 4)

    # --- delay on the lead, a dotted eighth, the classic
    dl = int(spb * 0.75 * SR)
    d = np.zeros_like(lead_bus)
    d[dl:] += lead_bus[:-dl] * 0.42
    d[dl * 2:] += lead_bus[:-dl * 2] * 0.17
    lead_bus = lead_bus + highpass_fft(d, 600)

    # --- sidechain. Duck everything that is not drums on each kick. This is
    # the single biggest thing that makes a bed sound produced rather than
    # assembled.
    duck = np.ones(n)
    for b in range(1, bars):
        for beat in range(4):
            i = int((b * bar + beat * spb) * SR)
            ln = int(spb * 0.85 * SR)
            if i + ln < n:
                duck[i:i + ln] = np.minimum(duck[i:i + ln],
                                            0.32 + 0.68 * np.linspace(0, 1, ln) ** 0.55)
    bass_bus *= duck
    pad_bus *= duck * 0.9
    lead_bus *= (0.55 + 0.45 * duck)

    tone = {"bright": (5200, 0.9), "warm": (2600, 1.0), "dark": (1700, 1.05)}[mood]
    mix = (mix * 0.95
           + lowpass_fft(bass_bus, 2600) * 0.85
           + lowpass_fft(pad_bus, tone[0]) * 0.32
           + lead_bus * 0.42 * tone[1])

    # --- a couple of reverb taps on the whole mix, cheap and good enough
    for delay, gain in ((0.031, 0.14), (0.057, 0.09), (0.089, 0.05)):
        k = int(delay * SR)
        mix[k:] += mix[:-k] * gain

    # Gentle top-end roll-off on the master. The bed sits UNDER text on a
    # phone; brightness past ~13k buys nothing and costs listening comfort.
    mix = lowpass_fft(mix, 13000)
    mix = np.tanh(mix * 1.25) * 0.92
    mix /= max(np.abs(mix).max(), 1e-9)
    mix *= 0.89
    mix[:400] *= np.linspace(0, 1, 400)
    mix[-int(0.4 * SR):] *= np.linspace(1, 0, int(0.4 * SR))
    return mix, total


TRACKS = {
    # (bpm, root midi, progression, bars, mood)
    "runway-lights":  (118, 57, [(0, "min"), (8, "maj"), (3, "maj"), (10, "maj")], 11, "bright"),
    "gate-a12":       (124, 53, [(0, "min"), (10, "maj"), (8, "maj"), (10, "maj")], 12, "bright"),
    "tarmac-sunrise": (112, 60, [(0, "maj"), (9, "min"), (5, "maj"), (7, "maj")], 11, "warm"),
    "red-eye":        (100, 55, [(0, "min"), (5, "min"), (8, "maj"), (3, "maj")], 10, "dark"),
}


def write(name):
    bpm, root, prog, bars, mood = TRACKS[name]
    print("  %-16s %3d bpm ..." % (name, bpm), end=" ", flush=True)
    audio, dur = build(name, bpm, root, prog, bars, mood)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    os.makedirs(OUT_DIR, exist_ok=True)
    # Bar 0 is a hi-hat count-in and the drop lands on bar 1. On a 10 second
    # reel two seconds of hats alone is 20% of the video with no energy, so the
    # file is named with the @offset that skips straight to the drop. The
    # count-in stays in the file in case a longer cut ever wants it.
    dest = os.path.join(OUT_DIR, "%s@%.1f.mp3" % (name, 4 * 60.0 / bpm))
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        f.write(pcm.tobytes())
        raw = f.name
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le",
                    "-ar", str(SR), "-ac", "1", "-i", raw,
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ac", "2", dest],
                   check=True)
    os.unlink(raw)
    print("%.1fs  %.0fKB" % (dur, os.path.getsize(dest) / 1024))


if __name__ == "__main__":
    want = [a for a in sys.argv[1:]] or list(TRACKS)
    print("writing original reel beds to %s" % OUT_DIR)
    for w in want:
        matches = [k for k in TRACKS if w in k]
        if not matches:
            raise SystemExit("no track matching %r (have: %s)" % (w, ", ".join(TRACKS)))
        for m in matches:
            write(m)
