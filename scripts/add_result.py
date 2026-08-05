#!/usr/bin/env python3
"""Append a game result to the current season file.

Usage:
    python3 scripts/add_result.py "BYU 45 Texas Tech 29" --week 7
    python3 scripts/add_result.py "Baylor 21 Texas Tech 14" -w 7 --gotw
    python3 scripts/add_result.py "Oregon ? Ohio State ?" -w 7 --note "OT, score TBD"

Team names are validated against the league file, so a typo fails loudly
instead of silently creating a phantom team.
"""
import argparse
import json
import re
import sys
from difflib import get_close_matches
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def all_teams(league):
    teams = []
    for conf_teams in league["conferences"].values():
        teams.extend(conf_teams)
    return teams


def resolve(name, teams):
    """Match a team name case-insensitively, suggesting alternatives on miss."""
    lookup = {t.lower(): t for t in teams}
    key = name.strip().lower()
    if key in lookup:
        return lookup[key]
    close = get_close_matches(key, lookup.keys(), n=3, cutoff=0.6)
    hint = "  Did you mean: %s" % ", ".join(lookup[c] for c in close) if close else ""
    sys.exit("Unknown team: %r\n%s" % (name.strip(), hint))


def parse(text, teams):
    """Parse 'Team A 45 Team B 29' where team names may contain spaces."""
    tokens = re.findall(r"(\d+|\?)", text)
    if len(tokens) != 2:
        sys.exit("Expected two scores (or '?'), found %d in: %r" % (len(tokens), text))

    # Split on the two score tokens, keeping the surrounding team names
    parts = re.split(r"\s*(?:\d+|\?)\s*", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) != 2:
        sys.exit("Could not separate team names in: %r" % text)

    a_name, b_name = resolve(parts[0], teams), resolve(parts[1], teams)
    a_score = None if tokens[0] == "?" else int(tokens[0])
    b_score = None if tokens[1] == "?" else int(tokens[1])
    return (a_name, a_score), (b_name, b_score)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", help='e.g. "BYU 45 Texas Tech 29"')
    ap.add_argument("-w", "--week", type=int, required=True)
    ap.add_argument("-s", "--season", type=int, default=2)
    ap.add_argument("--gotw", action="store_true", help="mark as Game of the Week")
    ap.add_argument("--note", default=None)
    args = ap.parse_args()

    with open(DATA / "league.json") as f:
        league = json.load(f)
    path = DATA / ("season_%02d.json" % args.season)
    with open(path) as f:
        season = json.load(f)

    teams = all_teams(league)
    (a, a_pts), (b, b_pts) = parse(args.result, teams)

    if a_pts is None or b_pts is None:
        winner, loser, score = a, b, None
        print("Score unknown — recording %s over %s, fill in later." % (a, b))
    elif a_pts == b_pts:
        sys.exit("Tie games aren't possible here — check the scores.")
    elif a_pts > b_pts:
        winner, loser, score = a, b, [a_pts, b_pts]
    else:
        winner, loser, score = b, a, [b_pts, a_pts]

    # Guard against entering the same matchup twice in one week
    for r in season["results"]:
        if r["week"] == args.week and {r["winner"], r["loser"]} == {a, b}:
            sys.exit("That matchup is already recorded for week %d." % args.week)

    entry = {"week": args.week, "winner": winner, "loser": loser, "score": score}
    if args.gotw:
        entry["gotw"] = True
    if args.note:
        entry["note"] = args.note

    season["results"].append(entry)
    season["results"].sort(key=lambda r: r["week"])
    season["current_week"] = max(season.get("current_week", 0), args.week)

    with open(path, "w") as f:
        json.dump(season, f, indent=2)
        f.write("\n")

    shown = "%d-%d" % tuple(score) if score else "score TBD"
    print("Week %d: %s beat %s, %s" % (args.week, winner, loser, shown))


if __name__ == "__main__":
    main()
