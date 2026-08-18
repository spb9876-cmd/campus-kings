#!/usr/bin/env python3
"""Coach profile pages.

Derives everything from the season data — records, GOTW appearances, playoff
runs, and a game log that names the opposing coach where there was one.
"""
import re
from collections import defaultdict

from points import coach_for, stamp

PROFILED = set()
clink = None     # injected by build.py
DYNAMIC = False  # injected by build.py; gates the search bar / sortable hooks


def _cname(league, cid):
    return next(c["name"] for c in league["coaches"] if c["id"] == cid)


def current_team(league, coach_id, season):
    """Most recent team this coach holds in the given season, if any."""
    entry = next((c for c in league["coaches"] if c["id"] == coach_id), None)
    if entry and entry.get("status") == "departed":
        return None
    best = None
    for t in league["tenures"]:
        if t["coach"] != coach_id:
            continue
        start = stamp(t["from"])[0]
        end = stamp(t["to"])[0] if t.get("to") else 99
        if start <= season <= end:
            if best is None or stamp(t["from"]) > stamp(best["from"]):
                best = t
    return best["team"] if best else None


def lifetime_rings(league, cid, prof):
    """Legacy titles from before the accredited cycle, plus any won inside it."""
    legacy = league.get("legacy_championships", {}).get(cid, 0)
    earned = prof.get(cid, {}).get("titles", 0)
    return legacy + earned


def exempt_tag(game):
    """FW (forfeit win) / SIM (simmed) marker from a game's note column.

    Exempt games still appear in logs and on the site -- badged -- but stay
    out of every user-vs-user W-L record.
    """
    note = (game.get("note") or "").upper()
    for t in ("FW", "SIM"):
        if re.search(r"\b%s\b" % t, note):
            return t
    return None


def gather(league, seasons):
    """Build a per-coach dossier keyed by coach id."""
    prof = defaultdict(lambda: {
        "games": [], "w": 0, "l": 0,
        "gotw_w": 0, "gotw_l": 0,
        "po_w": 0, "po_l": 0,
        "titles": 0, "runner_up": 0, "conf": 0,
    })

    for sdata in seasons:
        sn = sdata["season"]

        # Regular-season / league games
        for r in sdata.get("results", []):
            ex = exempt_tag(r)
            for team, won in ((r["winner"], True), (r["loser"], False)):
                cid = coach_for(league, team, sn, r["week"])
                if not cid:
                    continue
                opp = r["loser"] if won else r["winner"]
                opp_cid = coach_for(league, opp, sn, r["week"])
                p = prof[cid]
                if not ex:
                    p["w" if won else "l"] += 1
                    if r.get("gotw"):
                        p["gotw_w" if won else "gotw_l"] += 1
                p["games"].append({
                    "season": sn, "week": r["week"], "team": team,
                    "won": won, "opp": opp,
                    "opp_coach": _cname(league, opp_cid) if opp_cid else None,
                    "opp_cid": opp_cid,
                    "score": r["score"], "gotw": bool(r.get("gotw")),
                    "kind": "reg", "exempt": ex,
                })

        # Playoffs
        labels = {"R1": "Round 1", "QF": "Quarterfinal",
                  "SF": "Semifinal", "NC": "Championship"}
        for g in sdata.get("playoffs", []):
            ex = exempt_tag(g)
            for team, won in ((g["winner"], True), (g["loser"], False)):
                cid = coach_for(league, team, sn)
                if not cid:
                    continue
                opp = g["loser"] if won else g["winner"]
                opp_cid = coach_for(league, opp, sn)
                p = prof[cid]
                if not ex:
                    p["po_w" if won else "po_l"] += 1
                # a title decided by forfeit is still a title -- only the
                # user-vs-user W-L record leaves the game out
                if g["round"] == "NC":
                    p["titles" if won else "runner_up"] += 1
                p["games"].append({
                    "season": sn, "week": labels.get(g["round"], g["round"]),
                    "team": team, "won": won, "opp": opp,
                    "opp_coach": _cname(league, opp_cid) if opp_cid else None,
                    "opp_cid": opp_cid,
                    "score": g["score"], "gotw": False,
                    "kind": "playoff", "bowl": g.get("bowl"), "exempt": ex,
                })

        # Bowl games. Real games, so they count in the record and the log, but
        # they are outside the bracket and earn no Playoff Points.
        for bg in sdata.get("bowls") or []:
            ex = exempt_tag(bg)
            for team, won in ((bg["winner"], True), (bg["loser"], False)):
                cid = coach_for(league, team, sn)
                if not cid:
                    continue
                opp = bg["loser"] if won else bg["winner"]
                opp_cid = coach_for(league, opp, sn)
                p = prof[cid]
                if not ex:
                    p["w" if won else "l"] += 1
                p["games"].append({
                    "season": sn, "week": bg.get("bowl", "Bowl"),
                    "team": team, "won": won, "opp": opp,
                    "opp_coach": _cname(league, opp_cid) if opp_cid else None,
                    "opp_cid": opp_cid,
                    "score": bg.get("score"), "gotw": False,
                    "kind": "bowl", "bowl": bg.get("bowl"), "exempt": ex,
                })

        # Conference titles
        for cc in sdata.get("conference_championships", []):
            ex = exempt_tag(cc)
            for team, won in ((cc["winner"], True), (cc["loser"], False)):
                cid = coach_for(league, team, sn)
                if not cid:
                    continue
                opp = cc["loser"] if won else cc["winner"]
                opp_cid = coach_for(league, opp, sn)
                p = prof[cid]
                if not ex:
                    p["w" if won else "l"] += 1
                # like titles, a conference crown stands even on a forfeit
                if won:
                    p["conf"] += 1
                p["games"].append({
                    "season": sn, "week": "%s Title" % cc["conference"],
                    "team": team, "won": won, "opp": opp,
                    "opp_coach": _cname(league, opp_cid) if opp_cid else None,
                    "opp_cid": opp_cid,
                    "score": cc.get("score"), "gotw": False,
                    "kind": "conf", "conference": cc["conference"], "exempt": ex,
                })

    # Newest season first; within a season: regular games by week, then the
    # conference title, then the playoff run in bracket order.
    po_order = {"Round 1": 1, "Quarterfinal": 2, "Semifinal": 3, "Championship": 4}

    def sort_key(g):
        # Tier keeps the kinds apart so the third element is only ever
        # compared against its own type -- a bowl name is a string and a
        # regular-season week is an int, and mixing them raises TypeError.
        if g["kind"] == "playoff":
            return (-g["season"], 3, po_order.get(g["week"], 9))
        if g["kind"] == "conf":
            return (-g["season"], 2, 0)
        if g["kind"] == "bowl":
            return (-g["season"], 1, 0)
        return (-g["season"], 0, g["week"])

    for p in prof.values():
        p["games"].sort(key=sort_key)
    return prof


def index_page(league, prof, shell, bug, season):
    legacy = league.get("legacy_championships", {})
    rows = []
    for c in league["coaches"]:
        cid = c["id"]
        team = current_team(league, cid, season)
        p = prof.get(cid, {})
        rings = lifetime_rings(league, cid, prof)
        if not team and not rings:
            continue
        rows.append({
            "id": cid, "name": c["name"], "team": team,
            "rings": rings,
            "w": p.get("w", 0) + p.get("po_w", 0),
            "l": p.get("l", 0) + p.get("po_l", 0),
        })
    rows.sort(key=lambda r: (-r["rings"], -r["w"], r["name"]))

    search = ('<input class="searchbar" type="search" '
              'placeholder="Find a coach or team&hellip;" '
              'data-filter="#coachtable tr:not(:first-child)" '
              'aria-label="Find a coach or team">' if DYNAMIC else "")
    table_open = ('<table id="coachtable" class="sortable">' if DYNAMIC
                  else "<table>")
    b = ['<div class="pagehead"><h1 class="page">The <em>Coaches</em></h1>'
         '<p class="psub">Every coach, every game we have on record. Ring counts go '
         'all the way back; the Belt only counts the current 20-season run.</p></div>'
         f'<div class="section">{search}{table_open}'
         '<tr><th>Coach</th><th>Current team</th>'
         '<th>Rings</th><th>Tracked W&ndash;L</th></tr>']
    for r in rows:
        team = r["team"] or "<span style='color:var(--muted2)'>&mdash;</span>"
        rings = ("<span class='s'>%d</span>" % r["rings"]) if r["rings"] else \
                "<span style='color:var(--muted2)'>0</span>"
        rec = "%d&ndash;%d" % (r["w"], r["l"]) if (r["w"] or r["l"]) else \
              "<span style='color:var(--muted2)'>&mdash;</span>"
        b.append(f"<tr><td class='w'><a href='coach-{r['id']}.html' "
                 f"style='color:var(--gold)'>{r['name']}</a></td>"
                 f"<td style='color:var(--muted)'>{team}</td>"
                 f"<td class='s'>{rings}</td><td>{rec}</td></tr>")
    b.append("</table></div>")
    return shell("Coaches", "coaches.html", "\n".join(b), None, bug,
                 desc="Every Campus Kings coach — rings, records, and full "
                      "game logs.")


def coach_page(league, cid, prof, shell, bug, season):
    name = _cname(league, cid)
    team = current_team(league, cid, season)
    rings = lifetime_rings(league, cid, prof)
    p = prof.get(cid, {"games": [], "w": 0, "l": 0, "gotw_w": 0, "gotw_l": 0,
                       "po_w": 0, "po_l": 0, "titles": 0, "runner_up": 0, "conf": 0})

    stats = [
        (str(rings), "Lifetime rings"),
        ("%d-%d" % (p["w"], p["l"]), "League record"),
        ("%d-%d" % (p["gotw_w"], p["gotw_l"]), "Game of the Week"),
        ("%d-%d" % (p["po_w"], p["po_l"]), "Playoffs"),
        (str(p["conf"]), "Conference titles"),
    ]

    hero = (f'<div class="hero" style="padding:0">{"" }<div class="glow"></div>'
            f'<div class="inner" style="padding:52px 24px 44px">'
            f'<div class="eyebrow">{"Coach &middot; " + team if team else "Coach"}</div>'
            f'<h1 style="font-size:clamp(34px,5.4vw,56px)">{name}</h1>'
            f'</div></div><div class="glance"><div class="inner">'
            + "".join(f"<div class='cell'><div class='fig'>{v}</div>"
                      f"<div class='lab'>{k}</div></div>" for v, k in stats)
            + "</div></div>")

    b = []
    if p["titles"] or p["runner_up"]:
        bits = []
        if p["titles"]:
            bits.append("%d national title%s" % (p["titles"], "s" if p["titles"] > 1 else ""))
        if p["runner_up"]:
            bits.append("%d runner-up finish%s" % (p["runner_up"], "es" if p["runner_up"] > 1 else ""))
        b.append(f'<div class="section"><h2 class="sec">In the accredited cycle</h2>'
                 f'<div class="belt"><div class="lbl">Postseason</div>'
                 f'<div class="who" style="font-size:26px">{" &middot; ".join(bits)}</div>'
                 f'<div class="meta">Counted toward the Campus King Belt.</div></div></div>')

    b.append('<div class="section"><h2 class="sec">Game log</h2>')
    if not p["games"]:
        b.append('<p style="color:var(--muted);font-size:14px;margin:0">'
                 'No tracked games yet.</p>')
    else:
        cur = None
        b.append("<table>")
        for g in p["games"]:
            if g["season"] != cur:
                cur = g["season"]
                b.append(f"</table><div class='wklabel'>Season {cur}</div><table>")
            res = "W" if g["won"] else "L"
            col = "var(--gold)" if g["won"] else "var(--muted2)"
            sc = "%d&ndash;%d" % (tuple(g["score"]) if g["won"]
                                 else tuple(reversed(g["score"]))) if g["score"] else "TBD"
            opp = g["opp"]
            if g["opp_coach"]:
                nm = (clink(league, g.get("opp_cid"), g["opp_coach"])
                      if clink else g["opp_coach"])
                opp += f" <span style='color:var(--muted2)'>({nm})</span>"
            else:
                opp += " <span class='tag'>CPU</span>"
            tags = ""
            if g.get("exempt"):
                tags += '<span class="tag">%s</span>' % g["exempt"]
            if g["gotw"]:
                tags += '<span class="tag">GOTW</span>'
            # a bowl game already shows its name in the week column
            if g.get("bowl") and g["kind"] != "bowl":
                tags += '<span class="tag">%s</span>' % g["bowl"]
            if g["kind"] == "playoff":
                tags += '<span class="tag">Playoff</span>'
            if g["kind"] == "conf":
                tags += '<span class="tag">Conf Title</span>'
            if g["kind"] == "bowl":
                tags += '<span class="tag">Bowl</span>'
            wk = g["week"] if isinstance(g["week"], str) else "Week %s" % g["week"]
            b.append(f"<tr><td style='color:{col};font-weight:700;width:26px'>{res}</td>"
                     f"<td class='s' style='width:76px'>{sc}</td>"
                     f"<td class='w' style='width:118px'>{g['team']}</td>"
                     f"<td style='color:var(--muted)'>vs {opp}{tags}</td>"
                     f"<td style='color:var(--muted2);font-size:12px;text-align:right;"
                     f"white-space:nowrap'>{wk}</td></tr>")
        b.append("</table>")
    b.append('<div class="dt" style="padding-top:18px">'
             '<a href="coaches.html" style="color:var(--gold)">&larr; All coaches</a></div></div>')

    rec = "%d-%d" % (p["w"], p["l"])
    return shell(name, "coaches.html", "\n".join(b), hero, bug,
                 desc="%s — %s%s, %d lifetime ring%s in Campus Kings."
                      % (name, ("coach of %s, " % team) if team else "",
                         rec, rings, "" if rings == 1 else "s"),
                 path="coach-%s.html" % cid)
