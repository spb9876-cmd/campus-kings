#!/usr/bin/env python3
"""Generate the Campus Kings static site from data/.

    python3 scripts/build.py

Writes docs/*.html and copies media into docs/media/. Everything is derived
from data/ — never edit the generated HTML by hand.
"""
import json
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "docs"
MEDIA_SRC = Path("/mnt/user-data/outputs")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from points import compute, coach_for

CSS = """
:root{
  --bg:#08080a; --ink:#f4f2ea; --muted:#8d8b82; --muted2:#5a5852;
  --gold:#dfa839; --golddim:#a9863f; --rule:#212120; --card:#101012; --card2:#141416;
  --turf:#0d1410;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg)}
body{font-family:'Inter',system-ui,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px}

.navbar{border-bottom:1px solid var(--rule);position:sticky;top:0;z-index:20;
  background:rgba(8,8,10,.92);backdrop-filter:blur(8px)}
.navbar .inner{max-width:1000px;margin:0 auto;padding:16px 24px;display:flex;
  align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px}
.brand .name{font-family:'Anton',Impact,sans-serif;font-size:20px;letter-spacing:1.5px;text-transform:uppercase}
.brand .name span{color:var(--gold)}
nav{display:flex;gap:20px;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:var(--muted)}
nav a{padding:4px 0;border-bottom:1.5px solid transparent}
nav a:hover{color:var(--ink)}
nav a.on{color:var(--gold);border-bottom-color:var(--gold)}

.hero{position:relative;overflow:hidden;border-bottom:1px solid var(--rule);
  background:linear-gradient(180deg,var(--turf) 0%,var(--bg) 78%)}
.hero .field{position:absolute;inset:0;opacity:.5}
.hero .glow{position:absolute;inset:0;
  background:radial-gradient(ellipse 760px 320px at 50% 0,rgba(223,168,57,.18),transparent 70%)}
.hero .inner{position:relative;max-width:1000px;margin:0 auto;padding:76px 24px 64px;text-align:center}
.eyebrow{font-size:11px;letter-spacing:3.5px;text-transform:uppercase;color:var(--golddim);margin-bottom:20px}
.hero h1{font-family:'Anton',Impact,sans-serif;font-size:clamp(38px,6.4vw,68px);line-height:.97;
  text-transform:uppercase;margin:0 0 18px;letter-spacing:1px}
.hero h1 em{font-style:normal;color:var(--gold)}
.hero p.lede{max-width:620px;margin:0 auto;color:var(--muted);font-size:15.5px;line-height:1.65}
.hero .cta{margin-top:32px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.btn{font-size:12px;letter-spacing:1.6px;text-transform:uppercase;padding:11px 22px;
  border:1px solid var(--golddim);color:var(--gold);border-radius:2px;transition:.15s}
.btn:hover{background:var(--gold);color:#111}
.btn.ghost{border-color:var(--rule);color:var(--muted)}
.btn.ghost:hover{border-color:var(--muted);color:var(--ink)}

.glance{border-bottom:1px solid var(--rule);background:var(--card)}
.glance .inner{max-width:1000px;margin:0 auto;padding:0 24px;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
.glance .cell{padding:24px 8px;text-align:center;border-left:1px solid var(--rule)}
.glance .cell:first-child{border-left:none}
.glance .fig{font-family:'Anton',Impact,sans-serif;font-size:32px;color:var(--gold);line-height:1}
.glance .lab{font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:var(--muted2);margin-top:8px}

.section{padding:56px 0;border-bottom:1px solid var(--rule)}
.section:last-of-type{border-bottom:none}
h2.sec{display:flex;align-items:center;gap:14px;font-size:11.5px;letter-spacing:3px;
  font-weight:600;color:var(--gold);text-transform:uppercase;margin:0 0 26px}
h2.sec::after{content:"";flex:1;height:1px;background:var(--rule)}
h1.page{font-family:'Anton',Impact,sans-serif;font-size:clamp(32px,5vw,46px);line-height:1.03;
  text-transform:uppercase;margin:0 0 12px;letter-spacing:1px}
h1.page em{font-style:normal;color:var(--gold)}
.psub{color:var(--muted);font-size:15px;font-style:italic;margin:0;line-height:1.6;max-width:700px}
.pagehead{padding:52px 0 34px;border-bottom:1px solid var(--rule)}

.pillars{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1px;background:var(--rule)}
.pillar{background:var(--card);padding:26px 24px}
.pillar .n{font-family:'Anton',Impact,sans-serif;font-size:13px;color:var(--golddim);letter-spacing:2px}
.pillar h3{font-size:16px;margin:10px 0 9px;letter-spacing:.2px}
.pillar p{margin:0;font-size:13.5px;color:var(--muted);line-height:1.62}

.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px}
.step{border-top:2px solid var(--golddim);padding-top:16px}
.step .k{font-family:'Anton',Impact,sans-serif;font-size:15px;text-transform:uppercase;letter-spacing:1px;margin-bottom:7px}
.step p{margin:0;font-size:13px;color:var(--muted);line-height:1.6}

.belt{background:linear-gradient(135deg,var(--card2),var(--card));
  border:1px solid var(--rule);border-left:3px solid var(--gold);border-radius:3px;padding:26px 28px}
.belt .lbl{font-size:10.5px;letter-spacing:2.8px;color:var(--golddim);text-transform:uppercase}
.belt .who{font-family:'Anton',Impact,sans-serif;font-size:34px;margin:9px 0 5px;text-transform:uppercase;letter-spacing:.5px}
.belt .meta{font-size:13px;color:var(--muted);line-height:1.6;max-width:560px}

.row{display:flex;align-items:flex-start;gap:18px;padding:13px 4px;border-bottom:1px solid var(--rule)}
.row:last-child{border-bottom:none}
.num{font-family:'Anton',Impact,sans-serif;font-size:23px;color:var(--gold);width:38px;flex-shrink:0;line-height:1.15}
.bd{flex:1;min-width:0}
.tm{font-size:15px;font-weight:700}
.co{font-size:11px;color:var(--muted2);text-transform:uppercase;letter-spacing:.6px;margin-left:8px}
.dt{font-size:12.5px;color:var(--muted);margin-top:4px;line-height:1.5}
.rt{font-family:'Anton',Impact,sans-serif;font-size:15px;color:var(--golddim);flex-shrink:0;white-space:nowrap;padding-top:4px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:10.5px;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--muted2);font-weight:600;padding:0 10px 10px 0;border-bottom:1px solid var(--rule)}
td{padding:11px 10px 11px 0;border-bottom:1px solid var(--rule)}
td.w{font-weight:700}
td.s{font-family:'Anton',Impact,sans-serif;color:var(--gold);white-space:nowrap}
.tag{font-size:9.5px;letter-spacing:1px;text-transform:uppercase;color:var(--golddim);
  border:1px solid var(--rule);border-radius:2px;padding:2px 6px;margin-left:8px;white-space:nowrap}
.wklabel{font-size:10.5px;color:var(--golddim);letter-spacing:2.2px;text-transform:uppercase;margin:24px 0 7px}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(228px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--rule);border-radius:3px;overflow:hidden;
  display:block;transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--golddim);transform:translateY(-2px)}
.card img{width:100%;display:block;border-bottom:1px solid var(--rule);height:142px;object-fit:cover;object-position:top}
.card .body{padding:14px 16px}
.card .kind{font-size:10px;letter-spacing:2px;color:var(--golddim);text-transform:uppercase}
.card .ttl{font-size:14.5px;font-weight:700;margin:6px 0 5px}
.card .bl{font-size:12.5px;color:var(--muted);line-height:1.5}
.card .dte{font-size:10.5px;color:var(--muted2);margin-top:9px;letter-spacing:.5px}

.rulegrid{display:grid;grid-template-columns:200px 1fr;gap:40px;align-items:start}
.toc{position:sticky;top:78px;font-size:12.5px}
.toc a{display:block;padding:7px 0 7px 12px;color:var(--muted);border-left:1px solid var(--rule);line-height:1.4}
.toc a:hover{color:var(--gold);border-left-color:var(--golddim)}
.rule{padding:0 0 34px;margin-bottom:34px;border-bottom:1px solid var(--rule)}
.rule:last-child{border-bottom:none;margin-bottom:0}
.rule h3{font-family:'Anton',Impact,sans-serif;font-size:21px;text-transform:uppercase;
  letter-spacing:.8px;margin:0 0 14px;scroll-margin-top:90px}
.rule p{font-size:14px;color:var(--muted);line-height:1.7;margin:0 0 14px}
.rule ul{margin:0 0 14px;padding-left:0;list-style:none}
.rule li{position:relative;padding:8px 0 8px 20px;font-size:13.5px;color:var(--ink);
  line-height:1.6;border-bottom:1px solid var(--rule)}
.rule li:last-child{border-bottom:none}
.rule li::before{content:"";position:absolute;left:0;top:15px;width:7px;height:7px;
  border:1.5px solid var(--golddim);border-radius:1px}
.flag{background:rgba(223,168,57,.08);border:1px solid var(--golddim);border-radius:2px;
  padding:11px 14px;font-size:12.5px;color:var(--gold);margin-bottom:16px;line-height:1.55}
.foot-note{font-size:12.5px;color:var(--muted2);line-height:1.65;font-style:italic;margin:14px 0 0}
.rt-tables{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:20px;margin-bottom:16px}

footer{border-top:1px solid var(--rule);padding:26px 0 34px;font-size:10.5px;letter-spacing:2px;
  color:var(--muted2);text-transform:uppercase;text-align:center;line-height:1.9}
.ticker{position:relative;overflow:hidden;background:#0b0b0d;border-bottom:1px solid var(--rule);
  height:42px;display:flex;align-items:center}
.ticker::before{content:"Latest";position:absolute;left:0;top:0;bottom:0;z-index:3;
  display:flex;align-items:center;padding:0 14px;background:var(--gold);color:#0b0b0d;
  font-family:'Anton',Impact,sans-serif;font-size:11.5px;letter-spacing:2px;text-transform:uppercase}
.ticker::after{content:"";position:absolute;right:0;top:0;bottom:0;width:60px;z-index:2;
  background:linear-gradient(90deg,transparent,#0b0b0d);pointer-events:none}
.ticker .track{display:flex;align-items:center;gap:0;white-space:nowrap;
  padding-left:96px;animation:slide 52s linear infinite;will-change:transform}
.ticker:hover .track{animation-play-state:paused}
@keyframes slide{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.tk{display:inline-flex;align-items:center;gap:9px;padding:0 20px;font-size:12.5px;
  border-right:1px solid var(--rule)}
.tk .wk{font-size:9.5px;letter-spacing:1.4px;color:var(--muted2);text-transform:uppercase}
.tk .a{font-weight:700}
.tk .b{color:var(--muted)}
.tk .sc{font-family:'Anton',Impact,sans-serif;color:var(--gold);letter-spacing:.5px}
.tk .gw{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:#0b0b0d;
  background:var(--golddim);border-radius:2px;padding:2px 5px}
@media(prefers-reduced-motion:reduce){.ticker .track{animation:none}}
@media(max-width:720px){.rulegrid{grid-template-columns:1fr}.toc{display:none}}
"""

CROWN = ('<svg width="24" height="19" viewBox="0 0 34 26" fill="none">'
         '<path d="M2 22L4 8L11 14L17 4L23 14L30 8L32 22H2Z" stroke="#dfa839" '
         'stroke-width="2" stroke-linejoin="round"/>'
         '<line x1="2" y1="22" x2="32" y2="22" stroke="#dfa839" stroke-width="2"/></svg>')

FIELD = ('<svg class="field" width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 1000 380">'
         '<defs><linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
         '<stop offset="0" stop-color="#dfa839" stop-opacity=".22"/>'
         '<stop offset="1" stop-color="#dfa839" stop-opacity="0"/></linearGradient></defs>'
         + "".join('<line x1="%d" y1="0" x2="%d" y2="380" stroke="url(#fade)" stroke-width="%s"/>'
                   % (x, x, "1.4" if i % 2 == 0 else ".6")
                   for i, x in enumerate(range(50, 1000, 62)))
         + "".join('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#dfa839" '
                   'stroke-opacity=".1" stroke-width="1"/>' % (x, y, x + 12, y)
                   for y in (110, 210, 310) for x in range(20, 1000, 62))
         + "</svg>")


def ticker(season_data, limit=14):
    """Scrolling scorebug of the most recent results.

    The item list is emitted twice so the CSS translateX(-50%) loop is seamless.
    """
    results = season_data.get("results", [])
    if not results:
        return ""
    recent = sorted(results, key=lambda r: -r["week"])[:limit]

    items = []
    for r in recent:
        sc = "%d&ndash;%d" % tuple(r["score"]) if r["score"] else "TBD"
        gw = '<span class="gw">GOTW</span>' if r.get("gotw") else ""
        items.append(
            f'<span class="tk"><span class="wk">W{r["week"]}</span>'
            f'<span class="a">{r["winner"]}</span>'
            f'<span class="sc">{sc}</span>'
            f'<span class="b">{r["loser"]}</span>{gw}</span>'
        )
    strip = "".join(items)
    return f'<div class="ticker"><div class="track">{strip}{strip}</div></div>'


def shell(title, active, body, hero=None, bug=""):
    nav = ""
    for href, label in [("index.html", "Overview"), ("standings.html", "Standings"),
                        ("rules.html", "Rules"), ("history.html", "History")]:
        on = " class='on'" if href == active else ""
        nav += "<a href='%s'%s>%s</a>" % (href, on, label)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Campus Kings</title>
<meta name="description" content="Campus Kings — a 20-season CFB 27 online dynasty league.">
<meta property="og:title" content="Campus Kings">
<meta property="og:description" content="A 20-season CFB 27 online dynasty. Thirty coaches. One belt.">
<meta property="og:type" content="website">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<div class="navbar"><div class="inner">
<a class="brand" href="index.html">{CROWN}<span class="name">Campus <span>Kings</span></span></a>
<nav>{nav}</nav></div></div>
{bug}
{hero or ""}
<div class="wrap">{body}</div>
<footer>Campus Kings &middot; CFB 27 Online Dynasty<br>Updated {date.today().isoformat()}</footer>
</body></html>
"""


def load(n):
    return json.loads((DATA / n).read_text())


def cname(league, cid):
    return next(c["name"] for c in league["coaches"] if c["id"] == cid)


def league_records(season_data, league, season_no):
    rec = defaultdict(lambda: [0, 0])
    for r in season_data.get("results", []):
        rec[r["winner"]][0] += 1
        rec[r["loser"]][1] += 1
    out = []
    for team, (w, l) in rec.items():
        coach = coach_for(league, team, season_no)
        if coach:
            out.append({"team": team, "coach": coach, "w": w, "l": l})
    out.sort(key=lambda r: (-(r["w"] - r["l"]), -r["w"], r["team"]))
    return out


def build_index(league, s1, s2, content, pts, about, bug=""):
    hero = (f'<div class="hero">{FIELD}<div class="glow"></div><div class="inner">'
            f'<div class="eyebrow">Campus Kings &middot; Season '
            f'{league["league"]["current_season"]} in progress</div>'
            f'<h1>Thirty coaches.<br>Twenty seasons.<br><em>One belt.</em></h1>'
            f'<p class="lede">{about["intro"]}</p>'
            f'<div class="cta"><a class="btn" href="standings.html">Standings</a>'
            f'<a class="btn ghost" href="rules.html">Read the rules</a></div>'
            f'</div></div><div class="glance"><div class="inner">'
            + "".join(f"<div class='cell'><div class='fig'>{g['figure']}</div>"
                      f"<div class='lab'>{g['label']}</div></div>"
                      for g in about["at_a_glance"])
            + "</div></div>")

    champs = defaultdict(int)
    champs[coach_for(league, s1["champion"], 1)] += 1
    leader, titles = max(champs.items(), key=lambda kv: kv[1])

    b = ['<div class="section"><h2 class="sec">Who we are</h2><div class="pillars">'
         + "".join(f"<div class='pillar'><div class='n'>{p['num']}</div>"
                   f"<h3>{p['title']}</h3><p>{p['body']}</p></div>"
                   for p in about["pillars"]) + "</div></div>"]

    b.append('<div class="section"><h2 class="sec">How a week works</h2><div class="steps">'
             + "".join(f"<div class='step'><div class='k'>{s['step']}</div>"
                       f"<p>{s['text']}</p></div>" for s in about["how_it_works"])
             + "</div></div>")

    b.append(f"""<div class="section"><h2 class="sec">The Campus King Belt</h2>
<div class="belt"><div class="lbl">Current leader</div>
<div class="who">{cname(league, leader)}</div>
<div class="meta">{titles} national championship{'s' if titles != 1 else ''} &middot;
The belt goes to the coach with the most titles across
{league['league']['accredited_seasons']} accredited seasons. Rings matter most.</div></div>
<h2 class="sec" style="margin-top:36px">Playoff Points &middot; all time</h2>""")
    for r in pts[:8]:
        b.append(f"""<div class="row"><span class="num">{r['rank']}</span><div class="bd">
<span class="tm">{cname(league, r['coach'])}</span><span class="co">{r['team']}</span>
<div class="dt">{', '.join(r['breakdown'])}</div></div>
<span class="rt">{r['points']} pts</span></div>""")
    b.append('<div class="dt" style="padding-top:16px">'
             '<a href="standings.html" style="color:var(--gold)">Full standings &rarr;</a></div></div>')

    b.append('<div class="section"><h2 class="sec">Latest content</h2><div class="grid">')
    for c in content["content"][:4]:
        b.append(f"""<a class="card" href="media/{c['file']}">
<img src="media/{c['file']}" alt="{c['title']}" loading="lazy">
<div class="body"><div class="kind">{c['kind']} &middot; S{c['season']}</div>
<div class="ttl">{c['title']}</div><div class="bl">{c['blurb']}</div>
<div class="dte">{c['date']}</div></div></a>""")
    b.append("</div></div>")

    b.append(f"""<div class="section"><h2 class="sec">{about['join']['title']}</h2>
<p style="font-size:14.5px;color:var(--muted);line-height:1.7;max-width:660px;margin:0">
{about['join']['body']}</p></div>""")

    return shell("Overview", "index.html", "\n".join(b), hero, bug)


def build_rules(rules, bug=""):
    toc = "".join("<a href='#%s'>%s</a>" % (s["id"], s["title"]) for s in rules["sections"])
    body = []
    for s in rules["sections"]:
        body.append(f'<div class="rule"><h3 id="{s["id"]}">{s["title"]}</h3>')
        if s.get("flag"):
            body.append(f'<div class="flag">{s["flag"]}</div>')
        if s.get("body"):
            body.append(f'<p>{s["body"]}</p>')
        if s.get("items"):
            body.append("<ul>" + "".join("<li>%s</li>" % i for i in s["items"]) + "</ul>")
        tables = [s[k] for k in ("table", "table2", "table3") if s.get(k)]
        if tables:
            body.append('<div class="rt-tables">')
            for t in tables:
                body.append("<table><tr>" + "".join("<th>%s</th>" % h for h in t["head"]) + "</tr>")
                for row in t["rows"]:
                    body.append("<tr><td>%s</td><td class='s'>%s</td></tr>" % (row[0], row[1]))
                body.append("</table>")
            body.append("</div>")
        if s.get("footer"):
            body.append(f'<p class="foot-note">{s["footer"]}</p>')
        body.append("</div>")

    inner = (f'<div class="pagehead"><h1 class="page">Rules &amp; <em>Regulations</em></h1>'
             f'<p class="psub">{rules["preamble"]}</p></div>'
             f'<div class="section"><div class="rulegrid"><div class="toc">{toc}</div>'
             f'<div>{"".join(body)}</div></div></div>')
    return shell("Rules", "rules.html", inner, None, bug)


def build_standings(league, s2, pts, bug=""):
    recs = league_records(s2, league, 2)
    b = [f"""<div class="pagehead"><h1 class="page">Season Two <em>Standings</em></h1>
<p class="psub">Through week {s2.get('current_week', 0)}. League games only &mdash;
CPU results aren't tracked, so these won't match the in-game poll.</p></div>"""]

    b.append('<div class="section"><h2 class="sec">Head-to-head record</h2><table><tr>'
             '<th>#</th><th>Team</th><th>Coach</th><th>W&ndash;L</th></tr>')
    for i, r in enumerate(recs, 1):
        b.append(f"<tr><td>{i}</td><td class='w'>{r['team']}</td>"
                 f"<td style='color:var(--muted)'>{cname(league, r['coach'])}</td>"
                 f"<td class='s'>{r['w']}&ndash;{r['l']}</td></tr>")
    b.append("</table></div>")

    by = defaultdict(list)
    for r in s2.get("results", []):
        by[r["week"]].append(r)
    b.append('<div class="section"><h2 class="sec">Results by week</h2>')
    for wk in sorted(by, reverse=True):
        b.append(f'<div class="wklabel">Week {wk}</div><table>')
        for r in by[wk]:
            sc = "%d&ndash;%d" % tuple(r["score"]) if r["score"] else "TBD"
            tag = '<span class="tag">GOTW</span>' if r.get("gotw") else ""
            b.append(f"<tr><td class='w'>{r['winner']}{tag}</td>"
                     f"<td style='color:var(--muted)'>over {r['loser']}</td>"
                     f"<td class='s'>{sc}</td></tr>")
        b.append("</table>")
    b.append("</div>")

    b.append('<div class="section"><h2 class="sec">Playoff Points &middot; all time</h2><table><tr>'
             '<th>#</th><th>Coach</th><th>Team</th><th>Pts</th></tr>')
    for r in pts:
        b.append(f"<tr><td>{r['rank']}</td><td class='w'>{cname(league, r['coach'])}</td>"
                 f"<td style='color:var(--muted)'>{r['team']}</td>"
                 f"<td class='s'>{r['points']}</td></tr>")
    b.append("</table></div>")
    return shell("Standings", "standings.html", "\n".join(b), None, bug)


def build_history(league, s1, bug=""):
    nc = next(g for g in s1["playoffs"] if g["round"] == "NC")
    b = [f"""<div class="pagehead"><h1 class="page">League <em>History</em></h1>
<p class="psub">Champions, brackets, and how every coach got where they are.</p></div>
<div class="section"><div class="belt"><div class="lbl">Season One champion</div>
<div class="who">{s1['champion']} &middot; {cname(league, coach_for(league, s1['champion'], 1))}</div>
<div class="meta">Beat {s1['runner_up']} ({cname(league, coach_for(league, s1['runner_up'], 1))})
{nc['score'][0]}&ndash;{nc['score'][1]} in {nc.get('site', 'the final')} &mdash; as an 8 seed.</div>
</div></div>"""]

    labels = {"R1": "First round", "QF": "Quarterfinals",
              "SF": "Semifinals", "NC": "National Championship"}
    b.append('<div class="section"><h2 class="sec">Season One playoff bracket</h2>')
    for rnd in ["R1", "QF", "SF", "NC"]:
        b.append(f'<div class="wklabel">{labels[rnd]}</div><table>')
        for g in [x for x in s1["playoffs"] if x["round"] == rnd]:
            extra = "".join('<span class="tag">%s</span>' % g[k]
                            for k in ("bowl", "note") if g.get(k))
            b.append(f"<tr><td class='w'>{g['winner']}{extra}</td>"
                     f"<td style='color:var(--muted)'>over {g['loser']}</td>"
                     f"<td class='s'>{g['score'][0]}&ndash;{g['score'][1]}</td></tr>")
        b.append("</table>")
    b.append("</div>")

    b.append('<div class="section"><h2 class="sec">Coaching moves</h2><table><tr>'
             '<th>Team</th><th>Coach</th><th>From</th><th>Note</th></tr>')
    for t in league["tenures"]:
        if not t.get("note"):
            continue
        b.append(f"<tr><td class='w'>{t['team']}</td>"
                 f"<td style='color:var(--muted)'>{cname(league, t['coach'])}</td>"
                 f"<td class='s' style='font-size:13px'>{t['from']}</td>"
                 f"<td style='color:var(--muted);font-size:12.5px'>{t['note']}</td></tr>")
    b.append("</table></div>")
    return shell("History", "history.html", "\n".join(b), None, bug)


def main():
    league, s1, s2 = load("league.json"), load("season_01.json"), load("season_02.json")
    content, about, rules = load("content.json"), load("about.json"), load("rules.json")
    pts = compute(league, s1)
    bug = ticker(s2)

    SITE.mkdir(exist_ok=True)
    (SITE / "media").mkdir(exist_ok=True)
    # Tell GitHub Pages to serve these files as-is instead of running Jekyll
    (SITE / ".nojekyll").write_text("")
    copied = 0
    for c in content["content"]:
        src = MEDIA_SRC / c["file"]
        if src.exists():
            shutil.copy(src, SITE / "media" / c["file"])
            copied += 1

    (SITE / "index.html").write_text(build_index(league, s1, s2, content, pts, about, bug))
    (SITE / "standings.html").write_text(build_standings(league, s2, pts, bug))
    (SITE / "rules.html").write_text(build_rules(rules, bug))
    (SITE / "history.html").write_text(build_history(league, s1, bug))
    print("Built 4 pages, copied %d/%d media -> %s" % (copied, len(content["content"]), SITE))


if __name__ == "__main__":
    main()
