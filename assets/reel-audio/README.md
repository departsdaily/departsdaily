# Reel audio

The reel renderer mixes one file from this folder under every video, picked
deterministically per (date, origin, slot) so a re-render reuses the same track.

## The house rule (owner, Aug 12 2026)

**Calm only. No techno, ever.** These three beds are the whole approved set:

| File | Sound | bpm |
|---|---|---|
| `window-seat.mp3` | lo-fi Rhodes electric piano, brushes, upright bass, light swing, a little room tone | 72 |
| `coast-road.mp3` | bossa on nylon string, shaker, chords comping off the beat | 78 |
| `first-light.mp3` | kalimba and air, barely a groove, the bright one | 84 |

They replaced four EDM beds — `gate-a12`, `red-eye`, `runway-lights`,
`tarmac-sunrise` — which were deleted and **must not come back**. Four on the
floor at 120 bpm reads as a nightclub, and this account is a Sunday morning
looking at cheap flights. `scripts/make_reel_music.py` deletes any of those four
on sight, every run.

Adding a track is fine as long as it holds the brief: 70 to 90 bpm, major-family
harmony, no kick, no clap backbeat, nothing that builds, mixed to sit under text.

## Regenerating

    python3 scripts/make_reel_music.py            # the three above
    python3 scripts/make_reel_music.py window     # just one
    python3 scripts/make_reel_music.py --alts     # the calm alternates that lost

Or run the **Regenerate reel music** workflow from the Actions tab, which does
the same thing on a runner and commits the result. That is the easy path when
you are not at a machine with Python and ffmpeg.

Every track is synthesised from scratch, so there is no licence, no attribution,
no Content ID risk, and nobody who can change their terms later.

## Starting a track at its hook

These three start on the music, so they need no offset. If you ever add a track
that builds, put the offset in the **filename**:

    sunset-drive@12.mp3     -> starts 12 seconds in
    window-seat.mp3         -> starts at 0:00

A reel is 10 to 13 seconds; a track that spends 20 building up is useless here.
There is a short fade in so cutting into the middle never starts on a hard edge,
and a fade out at the end.

## Why the folder exists at all

**The Instagram publishing API cannot attach a track from Instagram's music
library.** Not ours, not anyone's — Meta does not expose it. So the only music a
scheduled reel can carry is a file that lives here.

Which means it has to be **licensed for commercial use**, because Departs Daily
is a commercial affiliate site. A copyright claim on a Reel mutes it or takes it
down, and repeated claims put the account at risk. Ours are original, which
sidesteps the whole question. Do not put a chart song in here.

With this folder empty, reels post with a silent audio track. They still work.
Music is an upgrade, not a requirement.
