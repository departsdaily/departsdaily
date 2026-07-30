# Reel audio

Drop `.mp3` / `.m4a` / `.wav` files in this folder and the reel renderer mixes
one under every video, picked deterministically per (date, origin, slot) so a
re-render reuses the same track.

## Start the track at its hook

A reel is 10 to 13 seconds. Most tracks spend the first 20 building up, so by
the time the good part arrives the video has ended. Put the offset in the
**filename**:

    sunset-drive@12.mp3     -> starts 12 seconds in
    big-energy.mp3          -> starts at 0:00

Preview the track, find where it kicks, rename the file. That is the whole
workflow. There is a short fade in so cutting into the middle never starts on a
hard edge, and a fade out at the end.

**The Instagram publishing API cannot attach a track from Instagram's music
library.** Not ours, not anyone's — Meta does not expose it. So the only music
a scheduled reel can carry is a file that lives here.

Which means it has to be **licensed for commercial use**, because Departs Daily
is a commercial affiliate site. A copyright claim on a Reel mutes it or takes it
down, and repeated claims put the account at risk. Safe sources: Epidemic Sound
or Artlist (paid, cleared for social), YouTube Audio Library or Pixabay Music
(free, check each track's terms), or something original.

Do not put a chart song in here.

With this folder empty, reels post with a silent audio track. They still work.
Music is an upgrade, not a requirement.
