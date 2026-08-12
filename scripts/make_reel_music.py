#!/usr/bin/env python3
"""Generate original music beds for the Instagram reels.

WHY THIS EXISTS. A reel needs audio and Departs Daily is a commercial site, so
the options were: pay a library, use Meta's Sound Collection (free, but cleared
for Meta platforms only and it has to be pulled by hand from a logged-in
account), or own the music outright. This is the third. Every track here is
synthesised from scratch, so there is no licence, no attribution, no Content ID
risk, and no third party who can change their terms later.

THE BRIEF (owner, Aug 12 2026): CALM. NO TECHNO, EVER. The first generation of
these beds was four-on-the-floor EDM at 100-124 bpm with a saw lead, a clap
backbeat and a sidechain pump. It read as a nightclub, not as a Sunday morning
looking at cheap flights. All four are DELETED and must not come back:
gate-a12, red-eye, runway-lights, tarmac-sunrise. See RETIRED below.

THE THREE BEDS THAT SHIP are in SHIPPED: window-seat, coast-road, first-light.
Those are the only tracks any Departs Daily Instagram output may use. The rules
they were built to:

  * no kick drum, no clap, no backbeat, no sidechain ducking
  * 70 to 84 bpm instead of 100 to 124
  * MAJOR-family harmony (maj7 / add9 / min7), progressions that resolve
  * the melody is played by a Rhodes electric piano, a nylon string or a
    kalimba — never a saw or a square
  * percussion is brushes or a soft shaker, mixed well under the music
  * peak-to-average around 5:1. The old beds were squashed to 2.7:1, and that
    squashing is most of what made them feel aggressive

WHY THIS PALETTE. Instagram's publishing API cannot attach a trending sound —
no API can — so music here will never win reach. Its only job is to not be the
reason someone swipes away. Warm lo-fi and bossa are what short-form travel
video actually sounds like, so they are the least likely to cost a view.

The tracks can be regenerated and tweaked. Change the tempo, change the
progression, re-run, and the reels have new music.

Still short-form first: there is no build-up and no count-in. Bar one is the
music, because a reel is 10 to 13 seconds and an intro is a wasted third of it.
That is why these files carry no `@offset` in the name — playback starts at 0.

Usage:
    python3 scripts/make_reel_music.py            # the three SHIPPED beds
    python3 scripts/make_reel_music.py window     # just one
    python3 scripts/make_reel_music.py --alts     # the unused calm alternates
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


def sine(freq, n, phase=0.0):
    return np.sin(2 * np.pi * freq * np.arange(n) / SR + phase)


def tri(freq, n):
    """Triangle by odd harmonics with 1/h^2 rolloff. Much softer than a saw,
    which is the whole point — a saw is what made the old beds abrasive."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, h in enumerate(range(1, 16, 2)):
        if freq * h > SR / 2:
            break
        out += ((-1) ** k) * np.sin(2 * np.pi * freq * h * t) / (h * h)
    return out * 0.81


def lowpass_fft(x, cutoff):
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


# ------------------------------------------------------------------ voices


def mallet(freq, dur=1.1, bright=1.0):
    """Marimba / kalimba shape. A struck bar is inharmonic — the partials sit
    near 1 : 3.9 : 9.2, not 1 : 2 : 3 — and the high ones die first. Getting
    that decay ordering right is most of what separates 'wooden mallet' from
    'organ note'."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, decay in ((1.0, 1.0, 4.2), (3.93, 0.30 * bright, 9.0),
                              (9.22, 0.11 * bright, 15.0)):
        f = freq * ratio
        if f > SR / 2:
            continue
        out += np.sin(2 * np.pi * f * t) * amp * np.exp(-t * decay)
    # The mallet head itself: a very short filtered thump, not a click.
    strike = np.random.RandomState(int(freq) % 97).randn(n) * np.exp(-t * 320) * 0.05
    out += lowpass_fft(strike, 2400)
    out *= np.minimum(1.0, np.arange(n) / max(1, int(0.004 * SR)))
    return out * 0.55


def pluck(freq, dur=1.4, damp=0.5, seed=0):
    """Karplus-Strong. This is the nylon-string / ukulele voice. Cheap, and it
    is genuinely the right algorithm for a plucked string rather than an
    imitation of one."""
    n = int(dur * SR)
    N = max(2, int(SR / freq))
    rs = np.random.RandomState(seed)
    buf = lowpass_fft(rs.randn(N), 3000)
    buf /= max(np.abs(buf).max(), 1e-9)
    out = np.zeros(n)
    idx = 0
    prev = 0.0
    for i in range(n):
        cur = buf[idx]
        out[i] = cur
        # one-pole averaging loop filter = the string losing its highs first
        nxt = (cur * (1.0 - damp * 0.5) + prev * damp * 0.5) * 0.996
        buf[idx] = nxt
        prev = cur
        idx = (idx + 1) % N
    out *= np.exp(-np.arange(n) / SR * 1.15)
    return lowpass_fft(out, 4200) * 0.42


def shaker(dur=0.09):
    """Soft shaker. Deliberately dull and quiet: it marks time without ever
    being the thing you notice."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rs = np.random.RandomState(11)
    s = rs.randn(n) * np.exp(-t * 46) * (1 - np.exp(-t * 700))
    return lowpass_fft(highpass_fft(s, 3800), 8600) * 0.10


def rim(dur=0.13):
    """A single soft wooden tap on beat one. Not a snare, not a clap — the old
    clap backbeat is exactly what made the last set feel like a workout."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 320 * t) * np.exp(-t * 42)
    air = np.random.RandomState(5).randn(n) * np.exp(-t * 150) * 0.25
    return lowpass_fft(body + air, 3200) * 0.11


def rhodes(freq, dur=1.8, bright=1.0):
    """Rhodes electric piano, by FM the way the real DX-era ones did it: one
    sine modulating another at a 1:1 ratio with the modulation index decaying
    much faster than the note. That fast-dying index IS the bell-like attack,
    and the pure sine left behind is the warm body. This is the single most
    native sound in short-form travel video."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    idx = 2.6 * bright * np.exp(-t * 13.0)          # bark, then get out of the way
    car = np.sin(2 * np.pi * freq * t + idx * np.sin(2 * np.pi * freq * t))
    body = np.sin(2 * np.pi * freq * t) * 0.45
    tine = np.sin(2 * np.pi * freq * 4.02 * t) * 0.09 * np.exp(-t * 22)
    out = (car * 0.8 + body + tine) * np.exp(-t * 1.9)
    out *= np.minimum(1.0, np.arange(n) / max(1, int(0.006 * SR)))
    return lowpass_fft(out, 5000) * 0.36


def kalimba(freq, dur=1.3):
    """Thumb piano. Nearly a pure sine with one high partial and a short woody
    click — brighter and smaller than the marimba, and it leaves more air."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.sin(2 * np.pi * freq * t) * np.exp(-t * 3.4)
    out += np.sin(2 * np.pi * freq * 5.4 * t) * 0.13 * np.exp(-t * 12)
    click = np.random.RandomState(int(freq) % 61).randn(n) * np.exp(-t * 480) * 0.045
    out += lowpass_fft(click, 3600)
    out *= np.minimum(1.0, np.arange(n) / max(1, int(0.003 * SR)))
    return out * 0.5


def brush(dur=0.22, swell=False):
    """Brushed snare. A swish, not a hit — noise that fades IN and then out,
    which is what a brush dragged across a head actually does."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rs = np.random.RandomState(17)
    shape = (np.exp(-t * 9) if not swell
             else np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5)
    s = rs.randn(n) * shape
    return lowpass_fft(highpass_fft(s, 1800), 7000) * (0.075 if not swell else 0.055)


def upright(freq, dur=0.9):
    """Double bass. Sine fundamental for the weight, a little triangle for the
    wood, and a short finger noise on the front so it reads as played."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.sin(2 * np.pi * freq * t) * np.exp(-t * 2.6)
    out += tri(freq, n) * 0.16 * np.exp(-t * 5.5)
    finger = np.random.RandomState(int(freq) % 53).randn(n) * np.exp(-t * 260) * 0.04
    out += lowpass_fft(finger, 1400)
    out *= np.minimum(1.0, np.arange(n) / max(1, int(0.007 * SR)))
    return out * 0.6


def vinyl(n, level=0.010):
    """Room tone. Filtered noise plus sparse crackle. Almost subliminal, and
    it is most of why a lo-fi bed sounds like a record instead of a plugin."""
    rs = np.random.RandomState(29)
    base = lowpass_fft(highpass_fft(rs.randn(n), 400), 6000) * level
    crackle = np.zeros(n)
    for i in rs.choice(n, size=max(1, n // 5200), replace=False):
        ln = min(n - i, int(0.0035 * SR))
        crackle[i:i + ln] += rs.randn(ln) * np.exp(-np.arange(ln) / SR * 900) * level * 5.5
    return base + lowpass_fft(crackle, 7000)


# ------------------------------------------------------------------ track


def build(bpm, root, prog, bars=8, mood="warm", voice="mallet", seedbase=0):
    """One finished track. `prog` is a list of (semitone offset from root,
    chord quality) per bar, cycling. Everything here is additive and gentle;
    there is no compressor and no ducking, because the bed sits under text at
    55% volume and dynamics are what keep it from feeling mechanical."""
    spb = 60.0 / bpm            # seconds per beat
    bar = spb * 4
    total = bar * bars
    n = int(total * SR) + 2 * SR
    pad_bus = np.zeros(n)
    low_bus = np.zeros(n)
    mel_bus = np.zeros(n)
    perc_bus = np.zeros(n)

    # Major-family voicings only. maj7 and add9 instead of plain triads: they
    # are what make a simple progression sound settled rather than jingly.
    QUAL = {"maj7": (0, 4, 7, 11), "add9": (0, 4, 7, 14), "min7": (0, 3, 7, 10),
            "maj": (0, 4, 7, 12), "sus2": (0, 2, 7, 12)}

    for b in range(bars):
        t0 = b * bar
        deg, qual = prog[b % len(prog)]
        chord = [root + deg + i for i in QUAL[qual]]

        # --- pad: the chord, slow in, slow out, the floor of the whole track
        pl = int(bar * 1.15 * SR)
        pad = np.zeros(pl)
        for k, note in enumerate(chord[:3]):
            f = midi(note)
            # Two voices a few cents apart. Slow, wide, and never in tune with
            # itself, which is what reads as "warm" rather than "synth".
            pad += tri(f * 0.9985, pl) * 0.30
            pad += tri(f * 1.0015, pl) * 0.30
            pad += sine(f * 2, pl) * 0.05
        pad *= env(pl, bar * 0.30, bar * 0.25, 0, bar * 0.40, sus=0.72)
        place(pad_bus, pad, t0)

        # --- low end: one soft sine root per bar, plus a fifth halfway. No
        # eighth-note bass line — that pulse is what drove the old tracks.
        for at, note, amp in ((0.0, chord[0] - 24, 1.0),
                              (bar * 0.5, chord[0] - 24 + 7, 0.45)):
            ln = int(bar * 0.62 * SR)
            f = midi(note)
            sig = (sine(f, ln) * 0.9 + sine(f * 2, ln) * 0.12)
            sig *= env(ln, 0.05, 0.25, 0, 0.55, sus=0.5) * amp
            place(low_bus, sig, t0 + at)
        # --- percussion: shaker on the offbeat eighths only, so it breathes
        # with the music instead of driving it, and one rim tap per bar.
        for eighth in range(8):
            if eighth % 2 == 0:
                continue
            place(perc_bus, shaker() * (0.9 if eighth == 3 else 0.65),
                  t0 + eighth * spb / 2)
        place(perc_bus, rim(), t0)

        # --- melody. Sparse on purpose: five or six notes a bar, with rests,
        # placed off the beat as often as on it. A run of sixteenths is what
        # made the old lead feel frantic.
        notes = chord + [chord[0] + 12, chord[1] + 12, chord[2] + 12]
        figure = [(0.0, 4), (0.75, 5), (1.5, 3), (2.0, 1), (3.0, 6), (3.5, 2)]
        if b % 2 == 1:
            figure = [(0.0, 5), (1.0, 3), (1.75, 6), (2.5, 4), (3.25, 1)]
        for beat_off, slot in figure:
            note = notes[slot % len(notes)]
            f = midi(note + 12)
            if voice == "mallet":
                sig = mallet(f, 1.15, bright=0.9)
            else:
                sig = pluck(f, 1.5, damp=0.55, seed=seedbase + slot + b)
            place(mel_bus, sig * 0.82, t0 + beat_off * spb)

    # --- a slow echo on the melody, one and a half beats, low in the mix. Not
    # the dotted-eighth delay of the old beds; this one is barely a repeat, it
    # just stops a sparse melody sounding bare.
    dl = int(spb * 1.5 * SR)
    d = np.zeros_like(mel_bus)
    d[dl:] += mel_bus[:-dl] * 0.26
    d[dl * 2:] += mel_bus[:-dl * 2] * 0.09
    mel_bus = mel_bus + lowpass_fft(d, 3200)

    tone = {"warm": 3000, "soft": 2300, "open": 3800}[mood]
    mix = (lowpass_fft(low_bus, 900) * 0.95
           + lowpass_fft(pad_bus, tone) * 0.34
           + lowpass_fft(mel_bus, 5200) * 0.62
           + perc_bus * 0.55)

    # --- reverb: longer and softer than the old three-tap. A calm bed wants
    # the room to be audible; a club bed wants it dry.
    rs = np.random.RandomState(23)
    for delay, gain in ((0.037, 0.16), (0.071, 0.13), (0.113, 0.10),
                        (0.181, 0.07), (0.269, 0.05), (0.397, 0.03)):
        k = int(delay * SR * (1.0 + rs.uniform(-0.04, 0.04)))
        mix[k:] += lowpass_fft(mix[:-k], 4200) * gain

    # Roll the top off. The bed sits UNDER text on a phone; brightness past
    # ~11k buys nothing here and is the first thing that reads as harsh.
    mix = lowpass_fft(mix, 11000)
    mix = np.tanh(mix * 0.85) * 0.95
    mix /= max(np.abs(mix).max(), 1e-9)
    mix *= 0.82
    fade_in, fade_out = int(0.25 * SR), int(1.2 * SR)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)
    mix[-fade_out:] *= np.linspace(1, 0, fade_out) ** 1.4
    return mix, total


VOICE_FN = {"mallet": lambda f, s: mallet(f, 1.15, bright=0.9),
            "kalimba": lambda f, s: kalimba(f, 1.3),
            "rhodes": lambda f, s: rhodes(f, 1.9),
            "pluck": lambda f, s: pluck(f, 1.5, damp=0.55, seed=s)}


def build_groove(bpm, root, prog, bars=8, voice="rhodes", seedbase=0,
                 swing=0.0, perc="brush", vinyl_level=0.0, comp=True,
                 pad_level=0.26, tone=2800):
    """The second family of beds: still calm, but with a FEEL — a walking-ish
    upright bass, chord comping off the beat, brushes instead of a shaker, and
    optional swing. This is the lo-fi / bossa lane, which is what short-form
    travel video actually sounds like. Same rules as the calm set: no kick, no
    backbeat, major-family harmony, nothing that builds."""
    spb = 60.0 / bpm
    bar = spb * 4
    total = bar * bars
    n = int(total * SR) + 2 * SR
    pad_bus = np.zeros(n)
    low_bus = np.zeros(n)
    mel_bus = np.zeros(n)
    cmp_bus = np.zeros(n)
    perc_bus = np.zeros(n)

    QUAL = {"maj7": (0, 4, 7, 11), "add9": (0, 4, 7, 14), "min7": (0, 3, 7, 10),
            "maj": (0, 4, 7, 12), "sus2": (0, 2, 7, 12), "dom9": (0, 4, 10, 14)}
    vfn = VOICE_FN[voice]

    def sw(beat):
        """Swing: push anything landing on an offbeat eighth later. Straight
        when swing=0."""
        frac = beat - int(beat)
        return beat + (swing if abs(frac - 0.5) < 1e-6 else 0.0)

    for b in range(bars):
        t0 = b * bar
        deg, qual = prog[b % len(prog)]
        chord = [root + deg + i for i in QUAL[qual]]

        # --- pad, quieter here than in the calm set: the comping is doing the
        # harmonic work, so the pad is only glue.
        pl = int(bar * 1.1 * SR)
        pad = np.zeros(pl)
        for note in chord[:3]:
            f = midi(note)
            pad += tri(f * 0.9985, pl) * 0.28 + tri(f * 1.0015, pl) * 0.28
        pad *= env(pl, bar * 0.28, bar * 0.25, 0, bar * 0.42, sus=0.7)
        place(pad_bus, pad, t0)

        # --- upright bass. Root on 1, fifth on 3, and a passing note into the
        # next bar on the back half of 4. That last note is the whole reason
        # this feels like a band and the calm set feels like a texture.
        nxt = prog[(b + 1) % len(prog)][0]
        for beat, note, amp, dur in ((0.0, chord[0] - 24, 1.0, spb * 1.7),
                                     (2.0, chord[0] - 24 + 7, 0.62, spb * 1.2),
                                     (3.5, root + nxt - 24 - 2, 0.42, spb * 0.55)):
            place(low_bus, upright(midi(note), dur) * amp, t0 + sw(beat) * spb)

        # --- comping: the chord, off the beat, short. Bossa and lo-fi both
        # live on the offbeat; putting these on the beat is what makes a
        # backing track sound like a metronome.
        if comp:
            hits = ([(1.5, 0.9), (2.5, 0.7), (3.75, 0.55)] if swing
                    else [(0.5, 0.85), (1.75, 0.7), (2.5, 0.8), (3.5, 0.6)])
            for beat, amp in hits:
                for k, note in enumerate(chord[1:4]):
                    sig = vfn(midi(note), seedbase + b * 7 + k)
                    place(cmp_bus, sig * 0.30 * amp, t0 + sw(beat) * spb
                          + k * 0.012)          # tiny roll, like a real hand

        # --- percussion
        if perc == "brush":
            for beat in (1.0, 3.0):
                place(perc_bus, brush(0.22), t0 + beat * spb)
            for beat in (0.5, 2.5):
                place(perc_bus, brush(spb * 0.9, swell=True), t0 + sw(beat) * spb)
        else:
            for e in range(8):
                amp = 0.9 if e in (0, 3, 6) else 0.5      # loose bossa accent
                place(perc_bus, shaker() * amp, t0 + sw(e / 2.0) * spb)
            place(perc_bus, rim(), t0 + 1.5 * spb)

        # --- melody, sparse and mostly off the beat
        notes = chord + [chord[0] + 12, chord[1] + 12, chord[2] + 12]
        figure = ([(0.5, 4), (1.5, 5), (2.5, 3), (3.5, 6)] if b % 2 == 0
                  else [(0.0, 5), (1.5, 6), (2.5, 4), (3.0, 2)])
        for beat, slot in figure:
            sig = vfn(midi(notes[slot % len(notes)] + 12), seedbase + slot + b * 3)
            place(mel_bus, sig * 0.7, t0 + sw(beat) * spb)

    # --- echo on the melody only, a beat and a half, well down in the mix
    dl = int(spb * 1.5 * SR)
    d = np.zeros_like(mel_bus)
    d[dl:] += mel_bus[:-dl] * 0.24
    mel_bus = mel_bus + lowpass_fft(d, 3000)

    mix = (lowpass_fft(low_bus, 1100) * 0.92
           + lowpass_fft(pad_bus, tone) * pad_level
           + lowpass_fft(cmp_bus, 4200) * 0.55
           + lowpass_fft(mel_bus, 5200) * 0.55
           + perc_bus * 0.62)

    rs = np.random.RandomState(23)
    for delay, gain in ((0.037, 0.15), (0.071, 0.12), (0.113, 0.09),
                        (0.181, 0.06), (0.269, 0.04)):
        k = int(delay * SR * (1.0 + rs.uniform(-0.04, 0.04)))
        mix[k:] += lowpass_fft(mix[:-k], 4200) * gain

    if vinyl_level:
        mix += vinyl(len(mix), vinyl_level)

    mix = lowpass_fft(mix, 10500)
    mix = np.tanh(mix * 0.9) * 0.95
    mix /= max(np.abs(mix).max(), 1e-9)
    mix *= 0.82
    fi, fo = int(0.25 * SR), int(1.2 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo) ** 1.4
    return mix, total


TRACKS = {
    # (bpm, root midi, progression, bars, mood, voice)
    # sunny-calm  — C major, I  V  vi  IV. The most settled progression there
    #               is, played on mallets. This is the default-feeling one.
    "sunny-calm":   (76, 60, [(0, "maj7"), (7, "add9"), (9, "min7"), (5, "maj7")],
                     8, "warm", "mallet", 11),
    # island-breeze — F major, IV  I  V  I with a sus. Nylon-string pluck,
    #               slightly slower, the one that sounds like somewhere warm.
    "island-breeze": (70, 65, [(5, "maj7"), (0, "add9"), (7, "sus2"), (0, "maj7")],
                      8, "soft", "pluck", 41),
    # morning-glow — G major, I  IV  vi  V, a touch brighter and a touch
    #               quicker, mallets again. The "today is a good day" one.
    "morning-glow": (84, 67, [(0, "add9"), (5, "maj7"), (9, "min7"), (7, "maj7")],
                     8, "open", "mallet", 73),
}

# SET B — the lo-fi / bossa lane. Same calm brief, wider palette, and a feel
# rather than a texture. Built Aug 12 2026 so the owner could hear both sets
# side by side before choosing which three ship.
GROOVE_TRACKS = {
    # (bpm, root, progression, bars, voice, seed, swing, perc, vinyl, comp)
    # window-seat  — lo-fi Rhodes, swung, room tone. The most native sound in
    #                short-form travel video, and the safest daily default.
    "window-seat":  (72, 60, [(0, "maj7"), (9, "min7"), (5, "maj7"), (7, "dom9")],
                     8, "rhodes", 13, 0.055, "brush", 0.011, True),
    # coast-road   — bossa on nylon string, straight eighths, shaker. This is
    #                the one that sounds like somewhere warm.
    "coast-road":   (78, 65, [(0, "maj7"), (7, "dom9"), (0, "maj7"), (5, "maj7")],
                     8, "pluck", 47, 0.0, "shaker", 0.0, True),
    # first-light  — kalimba and air. Barely a groove; the bright, hopeful one
    #                to break up two busier beds.
    "first-light":  (84, 67, [(0, "add9"), (5, "maj7"), (9, "min7"), (7, "maj7")],
                     8, "kalimba", 91, 0.0, "shaker", 0.0, False),
}

# The four EDM beds these replaced. Deleted from the repo Aug 12 2026 on the
# owner's call ("get rid of the techno"). Nothing may reintroduce them: the
# regenerate workflow deletes any file whose name starts with one of these.
RETIRED = ("gate-a12", "red-eye", "runway-lights", "tarmac-sunrise")

# The only tracks that ship. Everything in TRACKS above is a calm alternate
# that was auditioned and not chosen — kept because it costs nothing to keep
# and it documents what was rejected, but it is NOT written by default.
SHIPPED = ("window-seat", "coast-road", "first-light")


def sweep_retired(verbose=True):
    """Delete any retired EDM bed still sitting in the audio folder. Called on
    every run, because the renderer picks whatever it finds — one stray file is
    all it takes for a techno bed to end up under a post again."""
    gone = []
    if not os.path.isdir(OUT_DIR):
        return gone
    for f in sorted(os.listdir(OUT_DIR)):
        if any(f.startswith(r) for r in RETIRED):
            os.remove(os.path.join(OUT_DIR, f))
            gone.append(f)
    if gone and verbose:
        print("removed retired EDM beds: %s" % ", ".join(gone))
    return gone


def write(name):
    if name in TRACKS:
        bpm, root, prog, bars, mood, voice, seed = TRACKS[name]
        print("  %-16s %3d bpm %-7s ..." % (name, bpm, voice), end=" ", flush=True)
        audio, dur = build(bpm, root, prog, bars, mood, voice, seed)
    else:
        (bpm, root, prog, bars, voice, seed, swing, perc,
         vin, comp) = GROOVE_TRACKS[name]
        print("  %-16s %3d bpm %-7s ..." % (name, bpm, voice), end=" ", flush=True)
        audio, dur = build_groove(bpm, root, prog, bars, voice, seed,
                                  swing, perc, vin, comp)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    os.makedirs(OUT_DIR, exist_ok=True)
    # No `@offset` in the name: these start on the music, so playback starts
    # at 0. render_reel.py reads any offset from the filename and defaults to 0.
    dest = os.path.join(OUT_DIR, "%s.mp3" % name)
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
    ALL = dict(TRACKS, **GROOVE_TRACKS)
    args = sys.argv[1:]
    if "--alts" in args:
        args = [a for a in args if a != "--alts"] or list(TRACKS)
    want = args or list(SHIPPED)
    print("writing original reel beds to %s" % OUT_DIR)
    sweep_retired()
    for w in want:
        matches = [k for k in ALL if w in k]
        if not matches:
            sys.exit("no track matching %r (have: %s)" % (w, ", ".join(ALL)))
        for m in matches:
            write(m)
    print("done")
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
