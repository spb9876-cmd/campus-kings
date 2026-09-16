"""CK Uncensored board generator.

Edit EDITION and CARDS, run `python make_uncensored.py`, and it renders
ck_uncensored_<edition>.png (1122x1402, same canvas as the series) via
headless Edge. Quotes must be VERBATIM from the chat -- that's the format.
"""
import subprocess, time
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

EDITION = "6.0"

# (name, badge_color, card_bg, context, quote, doodle, target)
CARDS = [
    ("JT", "#7a3fb5", "#e9dcf7",
     "two weeks before walking into Norman and beating the two-time champ by eighteen",
     "Na I know I suck lol", "🍷",
     "Aged like fine wine"),
    ("BAWCE", "#2f6fd0", "#d8e9fb",
     "@everyone, an hour before losing the SEC title game 23&ndash;21&hellip; the follow-up: &ldquo;Good game&rdquo;",
     "tune in to watch Stew get his ass beat lol", "🥛",
     "At Stew"),
    ("PAT", "#2f9e57", "#dcf3e2",
     "after the glitch reset scholarships league-wide &mdash; Stew's alibi: &ldquo;haven't turned it on in like 3 days&rdquo;",
     "Shit tanked my board lol", "📉",
     "At the recruiting glitch"),
    ("TAYNE", "#b03fa0", "#f6def0",
     "replying to Pat posting his A+ coordinators on expiring contracts",
     "I&rsquo;ll pay em", "💸",
     "At the champ's whole staff"),
    ("STEW", "#e08a1e", "#fdeec4",
     "sliding into Tayne's mentions the morning after the bracket dropped",
     "can I have my QB back?", "🙏",
     "At Tayne"),
    ("STATES", "#c23b3b", "#fbdfd8",
     "after the B1G title rematch went Bowzer's way &mdash; Bowzer's reply: &ldquo;damn not herpes lol&rdquo;",
     "3x&hellip;lol. You&rsquo;re like herpes. Keep coming bac", "🦠",
     "At Bowzer"),
    ("BHOG", "#3f7ab5", "#daeaf8",
     "filing a formal complaint over a phantom Baylor matchup &mdash; the admin ruling: &ldquo;You play a cpu not Baylor&rdquo;",
     "Oh so you fucked up the match up just like yall fucked up the free win last night. OOKAAYYY", "⚖️",
     "At Curt"),
    ("WORK", "#8a6a1b", "#fdf3c8",
     "seeing the twelve-team field without Texas in it",
     "Brah ain&rsquo;t no way 🤣 I lost one conference game beat a&amp;m still didn&rsquo;t make it in shit troll 🤣🤣🤣", "🚫",
     "At the committee"),
]

CARD_HTML = """
<div class="card" style="background:{bg}">
  <div class="tail {side}" style="background:{bg}"></div>
  <div class="head">
    <div class="badge" style="background:{badge}">{n}</div>
    <div class="who">
      <div class="nm" style="color:{badge}">{name}</div>
      <div class="ctx">{context}</div>
    </div>
    <div class="doodle">{doodle}</div>
  </div>
  <div class="quote">&ldquo;{quote}&rdquo;</div>
  <div class="pillwrap"><span class="pill">🎯 {target}</span></div>
</div>"""

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Luckiest+Guy&family=Permanent+Marker&family=Gochi+Hand&family=Patrick+Hand&display=swap" rel="stylesheet">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{width:1122px;height:1402px;background:#f6efdc;position:relative;overflow:hidden;
    font-family:'Patrick Hand',cursive;color:#1d1a14;padding:34px 40px 26px}}
  body::before{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;background:
    radial-gradient(circle at 12% 30%, rgba(180,160,120,.10) 0 60px, transparent 61px),
    radial-gradient(circle at 88% 12%, rgba(180,160,120,.09) 0 90px, transparent 91px),
    radial-gradient(circle at 70% 85%, rgba(180,160,120,.08) 0 70px, transparent 71px)}}
  header{{text-align:center;position:relative;margin-bottom:16px}}
  .crown{{position:absolute;left:26px;top:-6px;font-size:52px;transform:rotate(-14deg)}}
  .d1{{position:absolute;right:30px;top:-2px;font-family:'Permanent Marker';font-size:30px;
    color:#5b2fb5;transform:rotate(8deg)}}
  h1{{font-family:'Luckiest Guy';font-size:88px;line-height:.95;letter-spacing:2px;
    text-shadow:3px 3px 0 rgba(29,26,20,.18)}}
  h1 .a{{color:#e0a12f}} h1 .b{{color:#2c2437}} h1 .c{{color:#5b2fb5}}
  .subwrap{{display:inline-block;margin-top:10px;padding:4px 26px;background:
    linear-gradient(100deg, transparent 1%, #f2c744 2%, #f2c744 97%, transparent 98%);
    transform:rotate(-1deg)}}
  .sub{{font-family:'Permanent Marker';font-size:31px;color:#241f16}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px 24px;margin-top:14px}}
  .card{{position:relative;border:3.5px solid #241f16;border-radius:24px;
    padding:16px 20px 14px;box-shadow:5px 6px 0 rgba(36,31,22,.22)}}
  .tail{{position:absolute;bottom:-14px;width:26px;height:26px;border:3.5px solid #241f16;
    border-top:none;border-right:none;transform:skewX(28deg) rotate(-52deg)}}
  .tail.l{{left:44px}} .tail.r{{right:60px}}
  .head{{display:flex;align-items:flex-start;gap:12px}}
  .badge{{width:44px;height:44px;flex:0 0 44px;border-radius:50%;border:3px solid #241f16;
    color:#fff;font-family:'Luckiest Guy';font-size:26px;display:flex;align-items:center;
    justify-content:center;padding-top:4px;box-shadow:2px 2px 0 rgba(36,31,22,.25)}}
  .who{{flex:1;min-width:0}}
  .nm{{font-family:'Luckiest Guy';font-size:30px;letter-spacing:1.5px;line-height:1;
    text-shadow:1.5px 1.5px 0 rgba(29,26,20,.15)}}
  .ctx{{font-size:16.5px;line-height:1.18;color:#3c362b;margin-top:3px}}
  .doodle{{font-size:36px;flex:0 0 auto;transform:rotate(10deg)}}
  .quote{{font-family:'Gochi Hand';font-size:27px;line-height:1.14;font-weight:700;
    margin:9px 4px 10px;letter-spacing:.2px}}
  .pillwrap{{text-align:center}}
  .pill{{display:inline-block;background:#fffdf6;border:2.5px solid #241f16;border-radius:999px;
    padding:2px 18px 1px;font-size:18px;font-weight:700}}
  footer{{position:absolute;left:0;right:0;bottom:10px;display:flex;justify-content:space-between;
    align-items:center;padding:0 46px;font-family:'Permanent Marker';font-size:30px;color:#241f16}}
  footer .u{{text-decoration:underline}} footer .q{{color:#5b2fb5}}
</style></head><body>
<header>
  <div class="crown">👑</div>
  <div class="d1">100</div>
  <h1><span class="a">CK</span> <span class="b">UNCENSORED</span> <span class="c">{edition}</span></h1>
  <div class="subwrap"><span class="sub">Straight from the group chat, no filter.</span></div>
</header>
<div class="grid">{cards}</div>
<footer><span class="u">LOL</span><span>★</span><span>💬</span><span>〰〰</span><span class="q">?!?!</span><span>☺</span></footer>
</body></html>"""


def main():
    cards = "".join(
        CARD_HTML.format(n=i + 1, name=name, badge=badge, bg=bg, context=ctx,
                         quote=quote, doodle=doodle, target=target,
                         side="l" if i % 2 == 0 else "r")
        for i, (name, badge, bg, ctx, quote, doodle, target) in enumerate(CARDS))
    html_path = HERE / "ck_uncensored.source.html"
    html_path.write_text(PAGE.format(edition=EDITION, cards=cards), encoding="utf-8")
    out = HERE / ("ck_uncensored_%s.png" % EDITION.replace(".", ""))
    if out.exists():
        out.unlink()
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--virtual-time-budget=8000",
                    "--screenshot=" + str(out), "--window-size=1122,1402",
                    html_path.resolve().as_uri()],
                   check=True, timeout=120, capture_output=True)
    time.sleep(0.5)
    print(out.name, Image.open(out).size)


if __name__ == "__main__":
    main()
