#!/usr/bin/env python3
"""Compute Campus Kings Playoff Points from raw season data.

Nothing here is hand-entered: points are derived from the bracket, so the
standings can never drift out of sync with the results.
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

DATA = Path(__file__).resolve().parent.parent / "data"

ROUND_ORDER = ["R1", "QF", "SF", "NC"]
NEXT_ROUND = {"R1": "QF", "QF": "SF", "SF": "NC"}

_STAMP = re.compile(r"^S(\d+)W(\d+)$")


def stamp(s):
    """Parse a tenure stamp like 'S2W10' into a sortable (season, week) tuple.

    Must not be compared as a string: 'S2W10' < 'S2W2' lexically, which would
    order a week-10 move before a week-2 one.
    """
    m = _STAMP.match(s.strip())
    if not m:
        raise ValueError("bad tenure stamp %r - expected e.g. S2W10" % s)
    return int(m.group(1)), int(m.group(2))


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def team_conference(league, team):
    for conf, teams in league["conferences"].items():
        if team in teams:
            return conf
    return None


def coach_for(league, team, season, week=None):
    """Resolve which coach held a team during a given season.

    Pass `week` to resolve at week granularity instead. Stamps are treated as
    from-inclusive / to-exclusive, matching how moves are recorded: Cell's
    Auburn tenure ends S2W2 and his LSU tenure begins S2W2, so week 2 belongs
    to LSU. Without a week, a tenure counts for the whole season it ends in --
    which is what the points race wants, but it credits a coach with games his
    old team played as a CPU after he left, so the game logs pass a week.

    Returns None when nobody held the team then (CPU-controlled).
    """
    if week is None:
        matches = []
        for t in league["tenures"]:
            if t["team"] != team:
                continue
            start = stamp(t["from"])[0]
            end = stamp(t["to"])[0] if t.get("to") else 99
            if start <= season <= end:
                matches.append(t)
        if not matches:
            return None
        # Prefer the tenure that starts latest but still covers the season
        return sorted(matches, key=lambda t: stamp(t["from"]))[-1]["coach"]

    # Postseason weeks arrive as round labels ("NC", "Semifinal"); treat them
    # as falling at the very end of the season.
    wk = week if isinstance(week, int) else 99
    when = (season, wk)
    matches = []
    for t in league["tenures"]:
        if t["team"] != team:
            continue
        if stamp(t["from"]) <= when and (not t.get("to") or when < stamp(t["to"])):
            matches.append(t)
    if not matches:
        return None
    return sorted(matches, key=lambda t: stamp(t["from"]))[-1]["coach"]


def compute(league, season_data):
    pts = league["rules"]["playoff_points"]
    conf_bonus = league["rules"]["conference_bonus"]
    season = season_data["season"]

    # Determine how far each team advanced
    reached = defaultdict(lambda: None)
    for game in season_data.get("playoffs") or []:
        rnd = game["round"]
        for team in (game["winner"], game["loser"]):
            prev = reached[team]
            if prev is None or ROUND_ORDER.index(rnd) > ROUND_ORDER.index(prev):
                reached[team] = rnd

    # Winning a round *is* reaching the next one. Without this a first-round
    # winner would sit on a berth until his quarterfinal is entered, even though
    # he has already advanced and earned the round-two award.
    for game in season_data.get("playoffs") or []:
        nxt = NEXT_ROUND.get(game["round"])
        if not nxt:
            continue
        w = game["winner"]
        if reached[w] is None or ROUND_ORDER.index(nxt) > ROUND_ORDER.index(reached[w]):
            reached[w] = nxt

    # Byes: seeds 1-4 skip R1, so credit them as having reached QF minimum.
    # playoff_seeds is hand-entered (ingest.py doesn't produce it), so treat it
    # as optional -- a season whose bracket lands before the seeds are filled in
    # should build with a warning, not a KeyError.
    seeds = season_data.get("playoff_seeds") or {}
    if not seeds and not (season_data.get("playoff_byes") or []) \
            and __name__ == "__main__":
        print("(no playoff_seeds for S%d -- teams yet to play score nothing)\n"
              % season)
    # A bye means you are already in round two, so credit the quarterfinal.
    for team in season_data.get("playoff_byes") or []:
        if reached[team] is None:
            reached[team] = "QF"

    for seed, team in seeds.items():
        if reached[team] is None:
            # In the field but yet to play. Seeds 1-4 are already in round two by
            # virtue of the bye; everyone else has only the berth so far.
            reached[team] = "QF" if int(seed) <= 4 else "R1"

    # Conference champions earn their bonus the moment the title game is in,
    # bracket or not. Touching the defaultdict puts them in the pool with a
    # round of None, meaning "no playoff credit yet -- bonus only".
    for cc in season_data.get("conference_championships") or []:
        reached[cc["winner"]]

    scores = {}
    detail = {}
    for team, deepest in reached.items():
        total = 0
        parts = []
        idx = -1
        if deepest is not None:
            total = pts["make_playoffs"]
            parts = ["playoff berth +%d" % pts["make_playoffs"]]
            idx = ROUND_ORDER.index(deepest)
        won_title = any(
            g["round"] == "NC" and g["winner"] == team
            for g in season_data.get("playoffs") or []
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
        for cc in season_data.get("conference_championships") or []:
            if cc["winner"] == team:
                bonus = conf_bonus.get(cc["conference"], 0)
                if bonus:
                    total += bonus
                    parts.append("%s title +%d" % (cc["conference"], bonus))

        if total == 0:
            continue          # in the pool but nothing earned yet
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
            # reached[team], not `deepest` -- that name belongs to the loop
            # above and would hand every row the last team's round.
            "reached": reached[team],
            "won_title": any(g["round"] == "NC" and g["winner"] == team
                             for g in season_data.get("playoffs") or []),
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


def bracket_is_final(season_data):
    """True once the national championship game has been entered."""
    return any(g.get("round") == "NC" for g in season_data.get("playoffs") or [])


def completed_seasons(league):
    """Seasons that have a bracket to score.

    The ladder is cumulative -- a coach banks +1 for making the field, +2 once
    he is in round two, and so on -- so a season starts scoring the moment its
    bracket does, and the standings move round by round. Only the Belt waits for
    the title game, because only that decides a championship.

    This needs "playoff_seeds" in the season file: until a bye team plays its
    quarterfinal it appears in no game, and without the seed list it would score
    nothing while first-round losers scored a berth.
    """
    out = []
    for n in range(1, league["league"]["accredited_seasons"] + 1):
        f = DATA / ("season_%02d.json" % n)
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if (d.get("playoffs") or d.get("playoff_seeds")
                or d.get("conference_championships")):
            out.append(d)
    return out


def live_bracket(season_data):
    """Postseason games for a season still in progress, newest round first.

    Returns [] once the bracket is final -- at that point the season is scored
    normally and the finished bracket belongs on the history page instead.
    """
    games = season_data.get("playoffs") or []
    if not games or bracket_is_final(season_data):
        return []
    order = {r: i for i, r in enumerate(ROUND_ORDER)}
    return sorted(games, key=lambda g: order.get(g.get("round"), 9))


def compute_all(league, seasons):
    """Career Playoff Points: per-season totals summed by coach.

    Points are attributed to the coach who held the team that season, so a
    coach keeps what he earned even after switching programs.

    Ordering follows the published standings rules: points first, then most
    national championships, then most championship-game appearances, then most
    Final Four appearances, then most total playoff appearances.
    """
    def blank(cid, team=None):
        return {"coach": cid, "points": 0, "teams": [team] if team else [],
                "titles": 0, "runner_up": 0, "seasons": 0, "final_fours": 0}

    career = {}
    for sdata in seasons:
        for r in compute(league, sdata):
            c = career.setdefault(r["coach"], blank(r["coach"]))
            c["points"] += r["points"]
            if r["reached"] is not None:
                c["seasons"] += 1                  # total playoff appearances
                if ROUND_ORDER.index(r["reached"]) >= 2:
                    c["final_fours"] += 1
            if r["team"] not in c["teams"]:
                c["teams"].append(r["team"])
        # titles / runner-up straight from the bracket
        for g in sdata.get("playoffs", []):
            if g["round"] != "NC":
                continue
            for team, won in ((g["winner"], True), (g["loser"], False)):
                cid = coach_for(league, team, sdata["season"])
                if not cid:
                    continue
                c = career.setdefault(cid, blank(cid, team))
                c["titles" if won else "runner_up"] += 1

    for c in career.values():
        # championship-game appearances = won it or lost it
        c["nc_apps"] = c["titles"] + c["runner_up"]

    def order(r):
        return (-r["points"], -r["titles"], -r["nc_apps"],
                -r["final_fours"], -r["seasons"], r["coach"])

    rows = sorted(career.values(), key=order)
    rank, last = 0, None
    for i, r in enumerate(rows, start=1):
        key = order(r)[:-1]        # everything but the alphabetical fallback
        if key != last:
            rank, last = i, key
        r["rank"] = rank
        r["team"] = r["teams"][-1] if r["teams"] else "&mdash;"
    return rows


def belt_race(rows):
    """Re-rank career rows for the Belt race: titles first, then points.

    compute_all() orders by points, which is the right shape for the Playoff
    Points ladder. The Belt is won on championships, so the race standings have
    to lead with titles and use points only to separate coaches on the same
    number of rings.
    """
    out = sorted(rows, key=lambda r: (-r["titles"], -r["points"],
                                      -r["runner_up"], r["coach"]))
    rank, last = 0, None
    for i, r in enumerate(out, start=1):
        key = (r["titles"], r["points"], r["runner_up"])
        if key != last:
            rank, last = i, key
        r["belt_rank"] = rank
    return out


def belt_leaders(rows):
    """Coaches tied for the most accredited-cycle championships."""
    if not rows:
        return [], 0
    best = max(r["titles"] for r in rows)
    if best == 0:
        return [], 0
    return [r for r in rows if r["titles"] == best], best


def main():
    league = load("league.json")
    seasons = completed_seasons(league)
    rows = compute_all(league, seasons)
    print("PLAYOFF POINTS — %d completed season(s)" % len(seasons))
    print("-" * 62)
    for r in rows:
        print("%3s  %-10s %-14s %3d pts  (%d title%s, %d RU, %d appearance%s)" % (
            r["rank"], r["coach"], r["team"], r["points"],
            r["titles"], "" if r["titles"] == 1 else "s",
            r["runner_up"], r["seasons"], "" if r["seasons"] == 1 else "s"))
    leaders, n = belt_leaders(rows)
    print("\nBelt: %s (%d)" % (", ".join(l["coach"] for l in leaders) or "nobody yet", n))
    return rows


def _legacy_main():
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
