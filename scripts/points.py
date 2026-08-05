#!/usr/bin/env python3
"""Compute Campus Kings Playoff Points from raw season data.

Nothing here is hand-entered: points are derived from the bracket, so the
standings can never drift out of sync with the results.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

DATA = Path(__file__).resolve().parent.parent / "data"

ROUND_ORDER = ["R1", "QF", "SF", "NC"]


def load(name):
    with open(DATA / name) as f:
        return json.load(f)


def team_conference(league, team):
    for conf, teams in league["conferences"].items():
        if team in teams:
            return conf
    return None


def coach_for(league, team, season):
    """Resolve which coach held a team during a given season."""
    matches = []
    for t in league["tenures"]:
        if t["team"] != team:
            continue
        start = int(t["from"][1])
        end = int(t["to"][1]) if t.get("to") else 99
        if start <= season <= end:
            matches.append(t)
    if not matches:
        return None
    # Prefer the tenure that starts latest but still covers the season
    return sorted(matches, key=lambda t: t["from"])[-1]["coach"]


def compute(league, season_data):
    pts = league["rules"]["playoff_points"]
    conf_bonus = league["rules"]["conference_bonus"]
    season = season_data["season"]

    # Determine how far each team advanced
    reached = defaultdict(lambda: None)
    for game in season_data["playoffs"]:
        rnd = game["round"]
        for team in (game["winner"], game["loser"]):
            prev = reached[team]
            if prev is None or ROUND_ORDER.index(rnd) > ROUND_ORDER.index(prev):
                reached[team] = rnd

    # Byes: seeds 1-4 skip R1, so credit them as having reached QF minimum
    for seed, team in season_data["playoff_seeds"].items():
        if int(seed) <= 4 and reached[team] is None:
            reached[team] = "QF"

    scores = {}
    detail = {}
    for team, deepest in reached.items():
        total = pts["make_playoffs"]
        parts = ["playoff berth +%d" % pts["make_playoffs"]]

        idx = ROUND_ORDER.index(deepest)
        won_title = any(
            g["round"] == "NC" and g["winner"] == team
            for g in season_data["playoffs"]
        )

        # Advancing *past* R1 earns the round-2 award, etc.
        if idx >= 1:
            total += pts["advance_round_2"]
            parts.append("round 2 +%d" % pts["advance_round_2"])
        if idx >= 2:
            total += pts["reach_final_four"]
            parts.append("final four +%d" % pts["reach_final_four"])
        if idx >= 3:
            total += pts["reach_championship"]
            parts.append("title game +%d" % pts["reach_championship"])
        if won_title:
            total += pts["win_championship"]
            parts.append("championship +%d" % pts["win_championship"])

        # Conference title bonus
        for cc in season_data["conference_championships"]:
            if cc["winner"] == team:
                bonus = conf_bonus.get(cc["conference"], 0)
                if bonus:
                    total += bonus
                    parts.append("%s title +%d" % (cc["conference"], bonus))

        scores[team] = total
        detail[team] = parts

    # CPU-held teams don't earn points toward the belt race
    inactive = set(league.get("inactive_teams", {}).get("S%d" % season, []))

    rows = []
    skipped = []
    for team, total in scores.items():
        coach = coach_for(league, team, season)
        if coach is None or team in inactive:
            skipped.append(team)
            continue
        rows.append({
            "team": team,
            "coach": coach,
            "points": total,
            "breakdown": detail[team],
        })

    if skipped and __name__ == "__main__":
        print("(excluded, no active coach: %s)\n" % ", ".join(sorted(skipped)))

    rows.sort(key=lambda r: (-r["points"], r["team"]))

    # Assign ranks with ties sharing a position
    rank = 0
    last = None
    for i, r in enumerate(rows, start=1):
        if r["points"] != last:
            rank = i
            last = r["points"]
        r["rank"] = rank
    return rows


def main():
    league = load("league.json")
    season = load("season_01.json")
    rows = compute(league, season)

    print("SEASON %d — PLAYOFF POINTS" % season["season"])
    print("-" * 62)
    for r in rows:
        print("%3s  %-14s %-9s %3d   %s" % (
            r["rank"], r["team"], r["coach"], r["points"], ", ".join(r["breakdown"])
        ))
    return rows


if __name__ == "__main__":
    main()
