#!/usr/bin/env python3
"""Coach profile pages.

Derives everything from the season data — records, GOTW appearances, playoff
runs, and a game log that names the opposing coach where there was one.
"""
from collections import defaultdict

from points import coach_for

PROFILED = set()
clink = None   # injected by build.py


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
        start = int(t["from"][1])
        end = int(t["to"][1]) if t.get("to") else 99
        if start <= season <= end:
            if best is None or t["from"] > best["from"]:
                best = t
    return best["team"] if best else None


def lifetime_rings(league, cid, prof):
    """Legacy titles from before the accredited cycle, plus any won inside it."""
    legacy = league.get("legacy_championships", {}).get(cid, 0)
    earned = prof.get(cid, {}).get("titles", 0)
    return legacy + earned


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
            for team, won in ((r["winner"], True), (r["loser"], False)):
                cid = coach_for(league, team, sn)
                if not cid:
                    continue
                opp = r["loser"] if won else r["winner"]
                opp_cid = coach_for(league, opp, sn)
                p = prof[cid]
                p["w" if won else "l"] += 1
                if r.get("gotw"):
                    p["gotw_w" if won else "gotw_l"] += 1
                p["games"].append({
                    "season": sn, "week": r["week"], "team": team,
                    "won": won, "opp": opp,
                    "opp_coach": _cname(league, opp_cid) if opp_cid else None,
                    "opp_cid": opp_cid,
                    "score": r["score"], "gotw": bool(r.get("gotw")),
                    "kind": "reg",
                })

        # Playoffs
        labels = {"R1": "Round 1", "QF": "Quarterfinal",
                  "SF": "Semifinal", "NC": "Championship"}
        for g in sdata.get("playoffs", []):
            for team, won in ((g["winner"], True), (g["loser"], False)):
                cid = coach_for(league, team, sn)
                if not cid:
                    continue
                opp = g["loser"] if won else g["winner"]
                opp_cid = coach_for(league, opp, sn)
                p = prof[cid]
                p["po_w" if won else "po_l"] += 1
                if g["round"] == "NC":
                    p["titles" if won else "runner_up"] += 1
                p["games"].append({
                    "season": sn, "week": labels.get(g["round"], g["round"]),
                    "team": team, "won": won, "opp": opp,
                    "opp_coach": _cname(league, opp_cid) if opp_cid else None,
                    "opp_cid": opp_cid,
                    "score": g["score"], "gotw": False,
                    "kind": "playoff", "bowl": g.get("bowl"),
                })

        # Conference titles
        for cc in sdata.get("conference_championships", []):
            cid = coach_for(league, cc["winner"], sn)
            if cid:
                prof[cid]["conf"] += 1

    # Newest season first; within a season, regular games by week then playoffs in order
    po_order = {"Round 1": 1, "Quarterfinal": 2, "Semifinal": 3, "Championship": 4}

    def sort_key(g):
        if g["kind"] == "playoff":
            return (-g["season"], 1, po_order.get(g["week"], 9))
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

    b = ['<div class="pagehead"><h1 class="page">The <em>Coaches</em></h1>'
         '<p class="psub">Lifetime championships, tracked records, and every game played. '
         'Ring counts span all league history &mdash; the Belt tracks the current '
         '20-season cycle only.</p></div>'
         '<div class="section"><table><tr><th>Coach</th><th>Current team</th>'
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
    return shell("Coaches", "coaches.html", "\n".join(b), None, bug)


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
            if g["gotw"]:
                tags += '<span class="tag">GOTW</span>'
            if g.get("bowl"):
                tags += '<span class="tag">%s</span>' % g["bowl"]
            if g["kind"] == "playoff":
                tags += '<span class="tag">Playoff</span>'
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

    return shell(name, "coaches.html", "\n".join(b), hero, bug)
