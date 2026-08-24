#!/usr/bin/env python3
"""Validate the results spreadsheet and fold it into season data.

Reads the published Google Sheet. Pass the URL directly or set SHEET_URL:

    python3 scripts/ingest.py --sheet "https://docs.google.com/.../pub?output=csv"
    SHEET_URL="https://..." python3 scripts/ingest.py

Validation is strict on purpose: a bad team name or a tie fails the build
rather than quietly publishing a wrong score.
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.request
from collections import defaultdict
from difflib import get_close_matches
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# Postseason stage labels for the Sheet's optional "stage" column.
#   blank      -> regular season, week must be a number
#   CONF:SEC   -> conference championship (bonus points keyed off the conference)
#   R1/QF/SF/NC-> playoff rounds
#   BOWL       -> non-playoff bowl between two user teams; put the bowl's name in
#                 the "bowl" column. Counts in records and game logs, scores nothing.
#   BYE        -> a team with a first-round bye: team in "winner", everything
#                 else blank. Four rows, read off the quarterfinal column of the
#                 bracket. This is the only thing results can't tell us -- a bye
#                 team plays no game until its quarterfinal, so without it the top
#                 four seeds would score nothing while first-round losers banked a
#                 berth. Teams that play in the first round need no row at all.
#   SEED       -> optional: full field with seed numbers, number in "week", team
#                 in "winner". BYE is the short version and is usually enough.
#
# The optional "note" column rides along onto every game entry. Two tokens in
# it are special (case-insensitive, anywhere in the note): "FW" marks a forfeit
# win and "SIM" a simmed game. The site badges those games and leaves them out
# of every user-vs-user W-L record; titles and conference crowns still stand.
STAGES = ("R1", "QF", "SF", "NC")
EXTRA_STAGES = ("BOWL", "SEED", "BYE")
# The points rules call the quarterfinal "round two", so accept R2 for it.
STAGE_ALIASES = {"R2": "QF", "R3": "SF", "R4": "NC", "QUARTERFINAL": "QF",
                 "SEMIFINAL": "SF", "SEMI": "SF", "FINAL": "NC",
                 "CHAMPIONSHIP": "NC", "TITLE": "NC"}


def all_teams(league):
    teams = []
    for conf_teams in league["conferences"].values():
        teams.extend(conf_teams)
    return teams


def read_rows(sheet_url):
    if "output=csv" not in sheet_url:
        sys.exit(
            "That doesn't look like a published CSV URL.\n"
            "In Sheets: File -> Share -> Publish to web -> pick the sheet -> "
            "format 'Comma-separated values (.csv)' -> Publish."
        )
    try:
        with urllib.request.urlopen(sheet_url, timeout=20) as r:
            text = r.read().decode("utf-8")
    except Exception as e:
        sys.exit("Could not fetch the Sheet: %s\n"
                 "Check that it's still published to the web." % e)
    return list(csv.DictReader(io.StringIO(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=os.environ.get("SHEET_URL"),
                    help="published Google Sheet CSV URL (or set SHEET_URL)")
    args = ap.parse_args()

    if not args.sheet:
        sys.exit("No Sheet URL. Pass --sheet \"<url>\" or set SHEET_URL.")

    league = json.loads((DATA / "league.json").read_text(encoding="utf-8"))
    teams = all_teams(league)
    lookup = {t.lower(): t for t in teams}

    rows = read_rows(args.sheet)
    errors = []
    by_season = defaultdict(list)
    conf_titles = defaultdict(list)
    playoffs = defaultdict(list)
    bowls = defaultdict(list)
    seeds = defaultdict(dict)
    byes = defaultdict(list)
    seen = set()

    for i, row in enumerate(rows, start=2):  # header is line 1
        if not (row.get("winner") or "").strip():
            continue

        stage_raw = (row.get("stage") or "").strip().upper()
        if stage_raw == "BYE":
            raw = (row.get("winner") or "").strip()
            t = lookup.get(raw.lower())
            if not t:
                close = get_close_matches(raw.lower(), lookup.keys(), n=1, cutoff=0.6)
                hint = " (did you mean %s?)" % lookup[close[0]] if close else ""
                errors.append("line %d: unknown team %r%s" % (i, raw, hint))
                continue
            try:
                sn = int(row["season"])
            except (ValueError, KeyError):
                errors.append("line %d: BYE needs a season" % i)
                continue
            if t in byes[sn]:
                errors.append("line %d: %s already has a bye" % (i, t))
                continue
            if len(byes[sn]) >= 4:
                errors.append("line %d: more than four byes in S%d" % (i, sn))
                continue
            byes[sn].append(t)
            continue

        if stage_raw == "SEED":
            raw = (row.get("winner") or "").strip()
            t = lookup.get(raw.lower())
            if not t:
                close = get_close_matches(raw.lower(), lookup.keys(), n=1, cutoff=0.6)
                hint = " (did you mean %s?)" % lookup[close[0]] if close else ""
                errors.append("line %d: unknown team %r%s" % (i, raw, hint))
                continue
            try:
                sn = int(row["season"])
                seed_no = int((row.get("week") or "").strip())
            except (ValueError, KeyError):
                errors.append("line %d: SEED needs a season and a seed number in "
                              "the week column" % i)
                continue
            if not 1 <= seed_no <= 12:
                errors.append("line %d: seed %d is outside 1-12" % (i, seed_no))
                continue
            if str(seed_no) in seeds[sn]:
                errors.append("line %d: seed %d already given to %s"
                              % (i, seed_no, seeds[sn][str(seed_no)]))
                continue
            if t in seeds[sn].values():
                errors.append("line %d: %s is already seeded" % (i, t))
                continue
            seeds[sn][str(seed_no)] = t
            continue

        def team(field):
            raw = (row.get(field) or "").strip()
            key = raw.lower()
            if key in lookup:
                return lookup[key]
            close = get_close_matches(key, lookup.keys(), n=1, cutoff=0.6)
            hint = " (did you mean %s?)" % lookup[close[0]] if close else ""
            errors.append("line %d: unknown team %r%s" % (i, raw, hint))
            return None

        w, l = team("winner"), team("loser")
        if not w or not l:
            continue
        if w == l:
            errors.append("line %d: %s listed as both winner and loser" % (i, w))
            continue

        try:
            season = int(row["season"])
        except (ValueError, KeyError):
            errors.append("line %d: season must be a number" % i)
            continue
        # A mistyped season number silently births a phantom season file and
        # the whole site flips its "current season" to it (it happened: a
        # season-5 row created season_05.json holding one game). league.json
        # knows the real current season; anything past it is a typo.
        current = league["league"]["current_season"]
        if not 1 <= season <= current:
            errors.append("line %d: season %d is outside 1-%d (league.json "
                          "current_season) — fix the season cell"
                          % (i, season, current))
            continue

        # stage routes the row: blank = regular season, otherwise postseason
        stage = (row.get("stage") or "").strip().upper()
        raw_week = (row.get("week") or "").strip()

        stage = STAGE_ALIASES.get(stage, stage)
        if (stage and stage not in STAGES and stage not in EXTRA_STAGES
                and not stage.startswith("CONF")):
            errors.append("line %d: unknown stage %r — use one of: %s, %s, or CONF:SEC"
                          % (i, row["stage"].strip(), ", ".join(STAGES),
                             ", ".join(EXTRA_STAGES)))
            continue

        if stage:
            week = raw_week or stage          # postseason: week is a label
        else:
            try:
                week = int(raw_week)
            except ValueError:
                errors.append("line %d: week must be a number for regular-season "
                              "games (leave stage blank), got %r" % (i, raw_week))
                continue

        ws, ls = (row.get("winner_score") or "").strip(), (row.get("loser_score") or "").strip()
        if ws and ls:
            ws, ls = int(ws), int(ls)
            if ws == ls:
                errors.append("line %d: tie score %d-%d is not possible" % (i, ws, ls))
                continue
            if ws < ls:
                errors.append(
                    "line %d: %s is in the winner column but scored fewer points "
                    "(%d-%d) — swap the columns" % (i, w, ws, ls)
                )
                continue
            score = [ws, ls]
        elif ws or ls:
            errors.append("line %d: only one score filled in — leave both blank or fill both" % i)
            continue
        else:
            score = None

        key = (season, week, frozenset([w, l]))
        if key in seen:
            errors.append("line %d: duplicate matchup %s vs %s in S%sW%s" % (i, w, l, season, week))
            continue
        seen.add(key)

        note = (row.get("note") or "").strip()
        if stage.startswith("CONF"):
            conf = stage.split(":", 1)[1].strip() if ":" in stage else ""
            if not conf:
                errors.append("line %d: conference title needs a conference, "
                              "e.g. CONF:SEC" % i)
                continue
            entry = {"conference": conf, "winner": w, "loser": l, "score": score}
            if note:
                entry["note"] = note
            conf_titles[season].append(entry)
        elif stage == "BOWL":
            entry = {"winner": w, "loser": l, "score": score,
                     "bowl": (row.get("bowl") or "").strip() or "Bowl"}
            if note:
                entry["note"] = note
            bowls[season].append(entry)
        elif stage:
            entry = {"round": stage, "winner": w, "loser": l, "score": score}
            if note:
                entry["note"] = note
            if (row.get("bowl") or "").strip():
                entry["bowl"] = row["bowl"].strip()
            playoffs[season].append(entry)
        else:
            entry = {"week": week, "winner": w, "loser": l, "score": score}
            if (row.get("gotw") or "").strip().lower() in ("y", "yes", "true", "1"):
                entry["gotw"] = True
            if note:
                entry["note"] = note
            by_season[season].append(entry)

    if errors:
        print("Spreadsheet has %d problem(s):\n" % len(errors), file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(1)

    order = {s: n for n, s in enumerate(STAGES)}
    all_seasons = (set(by_season) | set(conf_titles) | set(playoffs)
                   | set(bowls) | set(seeds) | set(byes))
    for season in sorted(all_seasons):
        path = DATA / ("season_%02d.json" % season)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {"season": season, "status": "in_progress"}

        results = by_season.get(season, [])
        if results:
            results.sort(key=lambda r: r["week"])
            data["results"] = results
            data["current_week"] = max(r["week"] for r in results)
        # Never let the Sheet shrink hand-entered postseason data. Season One's
        # bracket lives only in its season file -- if a partial set of playoff rows
        # ever appears in the Sheet, replacing eleven games with two would destroy
        # it silently. Same rule for conference titles.
        def keep_bigger(key, incoming, what):
            existing = data.get(key) or []
            if not incoming:
                return                      # Sheet said nothing; leave it alone
            if len(incoming) < len(existing):
                print("  REFUSED: Sheet has %d %s for S%d but the file already has "
                      "%d. Keeping the file. Add the missing rows, or delete "
                      "\"%s\" from season_%02d.json if the cut is intended."
                      % (len(incoming), what, season, len(existing), key, season),
                      file=sys.stderr)
                return
            data[key] = incoming

        keep_bigger("conference_championships", conf_titles.get(season), "conf titles")
        if playoffs.get(season):
            playoffs[season].sort(key=lambda g: order.get(g["round"], 9))
        keep_bigger("playoffs", playoffs.get(season), "playoff games")
        if bowls.get(season):
            bowls[season].sort(key=lambda g: g["bowl"])
            data["bowls"] = bowls[season]
        if seeds.get(season):
            data["playoff_seeds"] = {k: seeds[season][k]
                                     for k in sorted(seeds[season], key=int)}
        if byes.get(season):
            data["playoff_byes"] = byes[season]

        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("S%d: %d regular, %d conf title(s), %d playoff, %d bowl(s), "
              "%d seed(s), %d bye(s) -> %s"
              % (season, len(results), len(conf_titles.get(season, [])),
                 len(playoffs.get(season, [])), len(bowls.get(season, [])),
                 len(seeds.get(season, {})), len(byes.get(season, [])),
                 path.name))


if __name__ == "__main__":
    main()
