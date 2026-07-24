# Departs Daily Auto-Pilot

Fully autonomous 7AM pipeline: fetch fares → verify vs monthly baselines →
render branded slides → update departsdaily.com → post carousel + stories to
@cltdeparts. Runs on GitHub Actions cron. Site + images host free on GitHub
Pages under the custom domain departsdaily.com.

## One-time setup (you do these once, ~45 min)

1. **GitHub repo.** Create repo `departsdaily`, upload this folder. Settings →
   Pages → Deploy from branch → main, folder `/site`. Add custom domain
   departsdaily.com (GitHub shows the two DNS records to add at Porkbun).
2. **Travelpayouts (fares + affiliate money).** Sign up free at
   travelpayouts.com → profile → copy API token → repo Settings → Secrets and
   variables → Actions → new secret `TP_TOKEN`. Also copy your marker into
   site/js/affiliates.js `tpMarker` to monetize every flight link.
3. **Instagram professional + API.** In the Instagram app: Settings →
   Account type → Switch to professional (Creator). Then at
   developers.facebook.com: create app → add Instagram Graph API → connect
   @cltdeparts → generate a long-lived access token and note your IG user id →
   repo secrets `IG_TOKEN` and `IG_USER_ID`.
4. **Test run.** Repo → Actions tab → departs-daily-7am → Run workflow.
   Watch it fetch, render, deploy, and post.

## What it does every morning at 7:00 AM ET

- Pulls cheapest round trips for every route in `state/baselines.json`
- Keeps the top 4 fares that are ≥12% below that month's typical price
- Adds one SKIP warning (the most overpriced route) for credibility
- Enforces the 6-day no-repeat rule via `state/history.json`
- Renders the carousel (cover, board, CTA) + one story image per deal
- Updates the website deal board and publishes everything to Instagram with
  the verified/subject-to-change disclaimer baked into caption and slides

## Scaling to a new city

Add its routes to `state/baselines.json`, duplicate the workflow with the new
origin + that city's IG secrets. Same code, ten cities.

## Honest limitations

- Travelpayouts prices are cached search data — good, not perfect. The
  pipeline's ≥12% threshold plus monthly baselines filters most junk, but do a
  weekly spot-check of posted fares against Google Flights.
- Story link stickers can't be attached via API on all account types; stories
  post without stickers if unsupported (links then live in bio + site).
- Baselines are seed estimates for now — replace with DOT/BTS route data.
