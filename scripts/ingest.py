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

    league = json.loads((DATA / "league.json").read_text())
    teams = all_teams(league)
    lookup = {t.lower(): t for t in teams}

    rows = read_rows(args.sheet)
    errors = []
    by_season = defaultdict(list)
    seen = set()

    for i, row in enumerate(rows, start=2):  # header is line 1
        if not (row.get("winner") or "").strip():
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
            week = int(row["week"])
        except (ValueError, KeyError):
            errors.append("line %d: season and week must be numbers" % i)
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
            errors.append("line %d: duplicate matchup %s vs %s in S%dW%d" % (i, w, l, season, week))
            continue
        seen.add(key)

        entry = {"week": week, "winner": w, "loser": l, "score": score}
        if (row.get("gotw") or "").strip().lower() in ("y", "yes", "true", "1"):
            entry["gotw"] = True
        if (row.get("note") or "").strip():
            entry["note"] = row["note"].strip()
        by_season[season].append(entry)

    if errors:
        print("Spreadsheet has %d problem(s):\n" % len(errors), file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(1)

    for season, results in sorted(by_season.items()):
        path = DATA / ("season_%02d.json" % season)
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {"season": season, "status": "in_progress"}
        results.sort(key=lambda r: r["week"])
        data["results"] = results
        data["current_week"] = max(r["week"] for r in results)
        path.write_text(json.dumps(data, indent=2) + "\n")
        print("S%d: %d games through week %d -> %s"
              % (season, len(results), data["current_week"], path.name))


if __name__ == "__main__":
    main()
