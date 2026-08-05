# Campus Kings

Static site for the Campus Kings CFB 27 online dynasty. Everything on the site
is generated from `data/` — never edit the HTML in `docs/` by hand.

```
data/
  league.json      rules config, conferences, coaches, tenure history
  about.json       landing-page copy (pillars, how-it-works, at-a-glance)
  rules.json       the rulebook
  season_01.json   completed season: records, conf titles, bracket
  season_02.json   GENERATED from the Sheet by ingest.py
  content.json     manifest of published recaps/graphics
scripts/
  ingest.py        Google Sheet -> season JSON (validates hard)
  points.py        derives Playoff Points from the rules
  build.py         data/ -> docs/
docs/              generated output — this is what gets deployed
```

## Weekly workflow

```bash
export SHEET_URL="https://docs.google.com/.../pub?output=csv"
python3 scripts/ingest.py
python3 scripts/build.py
git add -A && git commit -m "week 8" && git push
```

Standings, records, and Playoff Points all recalculate themselves.

## Editing content

- **Scores** → the Google Sheet (see below).
- **Landing page copy** → `data/about.json`.
- **Rules** → `data/rules.json`.
- **New recap/graphic** → drop the PNG in `docs/media/`, add an entry to the top
  of `data/content.json`, rebuild:

```json
{
  "title": "Weeks 8-9 Recap",
  "kind": "Recap",
  "season": 2,
  "date": "2026-08-09",
  "file": "campus_kings_week8-9_recap.png",
  "blurb": "One line about what happened."
}
```

## Notes

- Playoff Points are computed from the rules, not typed in. The Season One
  output matches the standings LT posted in Discord exactly, including both tie
  groups — that's the regression test.
- CPU-held teams are excluded from the points race via `inactive_teams`.
- Season Two records are league games only, so they won't match the in-game
  poll. That's labeled on the page.
- Keep the site PG. The uncensored chat graphics stay in Discord.
