#!/usr/bin/env python3
"""Regression tests. Run before committing changes to points.py or league.json.

    python3 scripts/test_points.py

The Season One ordering below is not a guess — it's the standings LT posted in
the playoff-win-tracker channel. If a change to the scoring logic breaks this,
the change is wrong.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from points import load, compute, compute_all, completed_seasons, belt_leaders

# LT's posted Season One standings: rank -> coaches at that rank
EXPECTED_S1 = {
    1: {"stew"},
    2: {"lt"},
    3: {"dre"},
    4: {"curt"},
    5: {"work"},
    6: {"tayne", "purp", "states", "silingi"},
    10: {"cell", "iceman"},
}
EXPECTED_S1_POINTS = {"stew": 18, "lt": 11, "dre": 8, "curt": 6, "work": 5,
                      "tayne": 3, "purp": 3, "states": 3, "silingi": 3,
                      "cell": 1, "iceman": 1}

failures = []


def check(cond, msg):
    if cond:
        print("  pass  %s" % msg)
    else:
        print("  FAIL  %s" % msg)
        failures.append(msg)


def main():
    league = load("league.json")
    s1 = load("season_01.json")

    print("Season One single-season scoring")
    rows = compute(league, s1)
    by_rank = {}
    for r in rows:
        by_rank.setdefault(r["rank"], set()).add(r["coach"])
    check(by_rank == EXPECTED_S1,
          "ranks match LT's posted standings (incl. both tie groups)")
    if by_rank != EXPECTED_S1:
        print("        got:      %s" % by_rank)
        print("        expected: %s" % EXPECTED_S1)

    pts = {r["coach"]: r["points"] for r in rows}
    check(pts == EXPECTED_S1_POINTS, "point totals unchanged")
    if pts != EXPECTED_S1_POINTS:
        for k in sorted(set(pts) | set(EXPECTED_S1_POINTS)):
            if pts.get(k) != EXPECTED_S1_POINTS.get(k):
                print("        %s: got %s, expected %s"
                      % (k, pts.get(k), EXPECTED_S1_POINTS.get(k)))

    check(all(r["coach"] != "memphis" for r in rows)
          and not any(r["team"] == "Memphis" for r in rows),
          "CPU-held teams excluded from the points race")

    print("\nCareer scoring across completed seasons")
    seasons = completed_seasons(league)
    check(len(seasons) >= 1, "at least one completed season found")
    career = compute_all(league, seasons)
    check(career[0]["coach"] == "stew", "career leader is stew")
    check(career[0]["points"] >= 18, "career points >= single-season total")

    # The belt holder must be whoever actually has the most NC wins across the
    # completed seasons -- asserting a fixed count would go stale every season.
    from collections import Counter
    wins = Counter()
    for sd in seasons:
        for g in sd.get("playoffs") or []:
            if g["round"] == "NC":
                wins[g["winner"]] += 1
    top = max(wins.values()) if wins else 0
    leaders, n = belt_leaders(career)
    check(n == top, "belt title count matches the brackets (%d)" % top)
    check(all(l["titles"] == top for l in leaders) and leaders,
          "every belt holder has the top title count")

    # With only S1 complete, career must equal the single-season result.
    if len(seasons) == 1:
        check({r["coach"]: r["points"] for r in career} == EXPECTED_S1_POINTS,
              "career equals single-season when only one season is complete")

    print()
    if failures:
        print("%d FAILURE(S)" % len(failures))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
