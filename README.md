# Departs Daily — departsdaily.com

Charlotte's flight-deal board. Static site deployed on Netlify, refreshed
automatically every hour, around the clock.

## How the hourly refresh works

1. GitHub Actions runs `.github/workflows/daily-update.yml` every hour on the hour
   (also runnable manually from the Actions tab).
2. `scripts/update_deals.py` pulls the cheapest real round-trip fares for all
   30 tracked CLT routes from the Travelpayouts/Aviasales prices API and
   rewrites `site/js/deals-data.js` (deal board, weekly top-10, board stamp).
   Every fare shown is a real fare found in search cache — departure times
   come from the fare itself, nothing is invented.
3. The workflow commits the refreshed data file, zips `site/`, and deploys it
   straight to Netlify via the Netlify API.

If the API returns fewer than 10 routes, the script exits without writing —
yesterday's board (with its built-in auto-expiry) stays up instead of junk.

## Repo secrets required (Settings → Secrets and variables → Actions)

- `TP_TOKEN` — Travelpayouts API token
- `NETLIFY_AUTH_TOKEN` — Netlify personal access token
- `NETLIFY_SITE_ID` — `euphonious-pasca-35b9fd.netlify.app`

## Layout

- `site/` — the entire website (what gets deployed to Netlify)
- `site/js/deals-data.js` — GENERATED hourly; never hand-edit
- `site/js/affiliates.js` — affiliate link engine + all program config
- `scripts/update_deals.py` — the hourly board generator
- `gen_guides.py` — regenerates the 30 destination guide pages
