# Instagram Reels — two a day, per account

**Shipped July 29 2026.** Owner's rule: every account posts **two reels a day**,
rotating through three shapes. Live for `@cltdeparts` and `@atldeparts`, and
automatic for any city the moment its `ig_enabled` flips to true. No per city
work at all — reels ride the same origin config the carousel does.

## What runs when

| Time (ET) | What | Where it lives |
|---|---|---|
| 6:52 AM | board fetch, slides, carousel | `ig-post.yml` |
| 10:05 / 1:05 / 4:05 / 7:05 | story drip | `story-drip.yml` |
| **11:40 AM** | **reel, slot 0** | **`ig-reel.yml`** |
| **5:40 PM** | **reel, slot 1** | **`ig-reel.yml`** |

Reel slots sit in the gaps deliberately. The account now does something new
every two or three hours instead of everything at breakfast.

## One board, several edits

A reel is built from the **same `deals.json` the morning carousel posted**. It
never re-fetches fares. That is the point: the carousel, the stories, the site
and both reels all quote one verified board, so they cannot contradict each
other in the same feed an hour apart. `render_reel.py` refuses outright if the
board is not dated today, and `publish_reel.py` checks again before uploading.

## The three shapes

Rotation is `(date.toordinal() * 2 + slot) % 3` over `config/reels.json`
→ `order`. Deterministic, so re-running a failed slot rebuilds the *same* reel
rather than quietly switching shape. Period is three days, and the two slots in
one day can never land on the same shape.

| shape | length | what it is |
|---|---|---|
| `board` | ~13s | The whole board. Rows slide in one at a time, up to 7, then the sign off. |
| `spotlight` | ~10s | The single biggest discount. The price **counts down** from the typical fare to the real one, with both numbers on screen the whole way. |
| `destination` | ~13s | Top three deals as full frame city cards, each drifting slowly. |

All three end on the identical closing card (NOW BOARDING → departsdaily.com →
LINK IN BIO) so the sign off is the thing people learn to recognise.

Force one for a test: `REEL_SHAPE=spotlight python pipeline/render_reel.py`, or
the **shape** input on the workflow.

## How it is drawn

`pipeline/render_reel.py` draws 1080x1920 PIL frames and **pipes them straight
into ffmpeg as raw RGB** — no PNGs on disk, which is most of why a reel renders
in 15 to 20 seconds. Output is H.264 / yuv420p / 30fps / faststart, and lands
around **0.5 to 0.8 MB**, so staging them in the repo costs almost nothing. The
existing 14 day prune in `ig-post.yml` cleans them up with the slides.

Palette, tiles, badges and the disclaimer all come from the carousel renderer.
Same brand, moving.

**Safe area.** Instagram draws its own UI over a reel: the account row on top,
caption and buttons across the bottom, the action rail down the right. Nothing
readable is placed outside `config/reels.json` → `safe_area` (y 250 to 1440,
x 60 to 930). Get this wrong and the price sits under the Send button.

## Honesty rules, same as everywhere else

- Deal flagged rows only. A filler fare wearing motion and music would be
  exactly the lie the `deal` flag exists to prevent.
- Percentages are the computed `disc` off the board. Nothing is retyped.
- Unknown airline or times are omitted, never invented (`fmt_dates` mirrors the
  slide renderer line for line).
- The spotlight counter shows the typical fare **and** the deal fare together,
  so the drop is demonstrated rather than asserted.
- Caption is generated from the reel's own manifest (`reel_<slot>.json`), so the
  words cannot describe a fare the video does not show.
- Hashtags capped at **15**, per the owner rule and the id "0" bug in
  `departsdaily/ig-hashtag-cap-note.md`.

## Audio, and the thing you cannot have

**The Instagram publishing API cannot attach a track from Instagram's music
library.** Not just ours — Meta does not expose it to any app. A scheduled reel
can only carry audio that is a file in the repo.

So: drop commercially licensed files into `assets/reel-audio/` and the renderer
mixes one under each video at 55%, with a 1.5s fade out, picked
deterministically per (date, origin, slot). Empty folder means a **silent AAC
track** is muxed in anyway — a video with no audio stream at all is the edge
case Meta's transcoder is least happy with.

Silent reels do get watched. Music is a real upgrade and worth doing, but it is
a licensing decision, not a code one. See `assets/reel-audio/README.md`.

## Failure modes

The publisher does something the carousel publisher does not have to: **poll the
container until it is FINISHED.** Meta downloads the MP4 and transcodes it, and
`media_publish` on a container still `IN_PROGRESS` fails with a generic error
that tells you nothing. That poll is the reason reels get their own script.

| symptom | meaning | action |
|---|---|---|
| `MP4 never became reachable` in the wait step | Pages had not deployed the video | re-fire the slot; if daily, lengthen the wait |
| container id `"0"`, no error object | over 30 hashtags | count the tags, see `departsdaily/ig-hashtag-cap-note.md` |
| `status_code: ERROR` on the poll | Meta rejected the video itself | check the trail for its reason, then the encode settings |
| `code 200 "API access blocked"` | app or account level block | `departsdaily/ig-access-block-runbook.md`. Not self healing, do not re-fire |
| `slot N already posted today` | working as designed | nothing |

Every failure writes `out/reel-error-<ORIGIN>.json` and commits it, because
Actions logs age out and git is the only thing the ops sandbox can read.

**Double posting is impossible by design.** `state/reel-log-<ORIGIN>.json`
records the media id per slot per day, written the moment the publish returns. A
re-fired workflow in the same slot sees it and exits without a single API call.
Verified.

## Retry

Push `main` → `reel-trigger` (force). The push trigger exists because the ops
sandbox can reach git but not the Actions API. Slot comes from the clock on a
push (before 2PM ET → slot 0, after → slot 1), or from the **slot** input on a
manual run.

## Rate limits

Instagram allows 50 published posts per rolling 24 hours. A full day per account
is now 1 carousel + up to 7 stories + 2 reels = 10. Not close.

**Volume risk is the real one, not rate limits.** `@cltdeparts` took a
precautionary Meta restriction on Jul 28 and `@atldeparts` is days old. Going
from one post a day to four is the kind of step change automation flags notice.
If either account gets restricted, the first thing to try is dropping to one
reel a day: set `slots_per_day: 1` in `config/reels.json` and delete the
5:40 PM cron from `ig-reel.yml`.

## Worth building next

1. **Music.** The single biggest quality gap. Needs a license, not code.
2. **A first frame worth stopping on.** The hook card is typography. A real
   photo of the destination would stop the scroll far harder — same blocker as
   the Saturday guide carousel in `POSTING-SCHEDULE.md`: it needs a licensed
   image source, which is a decision before it is code.
3. **Watch through data.** Reels report `ig_reels_video_view_total_time` and
   average watch time. Once there are a few weeks of it, the shape rotation
   should stop being uniform and start favouring whatever holds people.
