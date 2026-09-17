"""CK Analyst -- the league's interactive content bot.

Listens in Discord and answers league questions within seconds, grounded in
the site's live data: "what happened in the Michigan game?", "predict Ole
Miss vs Oklahoma", "who leads the belt race?".

Triggers on any message that @mentions the bot, plus every message in
channels whose name contains "ask" (e.g. #ask-ck).

Brains: by default it shells out to the Claude Code CLI (`claude -p`), which
uses the owner's existing Claude subscription -- no API key needed. If
ANTHROPIC_API_KEY is set in the environment it calls the API directly
instead (that's the switch for 24/7 cloud hosting later).

Setup (one time):
  1. https://discord.com/developers/applications -> New Application ->
     Bot -> Reset Token. Enable the MESSAGE CONTENT intent under
     Privileged Gateway Intents.
  2. Put the token in tools/ck-desk/.env as:  DISCORD_TOKEN=xxxxx
     (.env is gitignored -- never commit it)
  3. Invite the bot: OAuth2 -> URL Generator -> scope "bot" -> permissions
     View Channels, Send Messages, Read Message History -> open the URL.
  4. pip install discord.py python-dotenv
  5. python tools/ck-desk/bot.py
"""
import asyncio
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import discord

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

TOKEN = os.environ.get("DISCORD_TOKEN")
API_KEY = os.environ.get("ANTHROPIC_API_KEY")          # optional: cloud mode
RAW = "https://raw.githubusercontent.com/spb9876-cmd/campus-kings/main/"
SITE = "https://spb9876-cmd.github.io/campus-kings/"
MAX_DISCORD = 1900                                     # under the 2000 cap
DATA_TTL = 300                                         # refresh grounding every 5 min

HOUSE_RULES = """You are the CK Analyst, the in-Discord voice of the
Campus Kings CFB 27 dynasty league site -- and you carry yourself like a
certain silver-tongued SEC talk-radio institution: the Paul
Finebaum-school of analysis. That means: dry, withering, gleefully
judgmental takes delivered with total certainty; you crown legends and
bury pretenders in the same sentence; you treat every result as either a
coronation or an indictment; you have a soft spot for the SEC and say so;
you address coaches like callers to your show. Sharp, never cruel --
roast the resume, not the person. Keep answers SHORT for Discord: a few
punchy sentences, max ~150 words, no headers. Never use @everyone or
@here.

Hard rules, non-negotiable:
- Facts come ONLY from the league data provided below. Scores, records,
  standings, dates: quote them exactly. If the data doesn't contain the
  answer, say so plainly and point to the site (%s).
- NEVER invent a score, stat, or quote.
- Games marked FW or SIM are forfeits/sims: they count on the site's logs
  but are excluded from user-vs-user records, and we don't narrate them as
  played games.
- The Campus King Belt goes to whoever has the most national titles after
  all 20 accredited seasons -- nobody "holds the belt" per season. Current
  race: check the data.
- Predictions are welcome and encouraged when asked -- make them fun,
  grounded in real results from the data, and clearly takes, not facts.
- If asked something outside league scope, deflect with charm in one line.
""" % SITE

_cache = {"at": 0.0, "text": ""}


def grounding():
    """League data blob, refreshed at most every DATA_TTL seconds."""
    import time
    if time.time() - _cache["at"] < DATA_TTL and _cache["text"]:
        return _cache["text"]
    parts = []
    names = ["data/league.json", "data/season_04.json",
             "docs/search-index.json", "data/content.json"]
    # Owner notes carry bracket context (seeds, bowl names, storylines) that
    # the raw results don't -- pull every note file that exists.
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/spb9876-cmd/campus-kings/"
            "contents/data/notes", headers={"User-Agent": "ck-desk"})
        listing = json.loads(urllib.request.urlopen(req, timeout=15).read())
        names += [f["path"] for f in listing if f["name"].endswith(".md")]
    except Exception:
        pass
    for name in names:
        try:
            req = urllib.request.Request(RAW + name,
                                         headers={"User-Agent": "ck-desk"})
            raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
            # search-index carries every historical result compactly
            parts.append("=== %s ===\n%s" % (name, raw))
        except Exception as e:
            parts.append("=== %s === (unavailable: %s)" % (name, e))
    _cache["text"] = "\n".join(parts)
    _cache["at"] = time.time()
    return _cache["text"]


def ask_claude(question, asker):
    prompt = ("%s\n\nLEAGUE DATA (authoritative):\n%s\n\n"
              "Coach %s asks: %s\n\nAnswer for Discord:"
              % (HOUSE_RULES, grounding(), asker, question))
    if API_KEY:
        import urllib.error
        body = json.dumps({
            "model": "claude-sonnet-5",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": API_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        out = json.loads(urllib.request.urlopen(req, timeout=120).read())
        return out["content"][0]["text"].strip()
    # Subscription mode: Claude Code CLI headless. The prompt goes in via
    # stdin -- as an argument it would blow Windows' command-length limit.
    import shutil
    cli = shutil.which("claude")
    if not cli:
        # Fall back to the CLI bundled with the Claude desktop app -- the
        # Store-packaged build keeps its "Roaming" under Packages\...
        candidates = []
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += Path(appdata, "Claude", "claude-code").glob("*/claude.exe")
        candidates += Path(local, "Packages").glob(
            "Claude_*/LocalCache/Roaming/Claude/claude-code/*/claude.exe")
        versions = sorted(candidates)
        cli = str(versions[-1]) if versions else None
    if not cli:
        raise RuntimeError("claude CLI not found on PATH or in the desktop app")
    r = subprocess.run([cli, "-p", "--model", "sonnet"],
                       input=prompt, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300] or "claude CLI failed")
    return r.stdout.strip()


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
busy = asyncio.Lock()


@client.event
async def on_ready():
    print("CK Analyst online as %s (mode: %s)"
          % (client.user, "API" if API_KEY else "Claude subscription"))


@client.event
async def on_message(msg):
    if msg.author.bot:
        return
    is_ask_channel = "ask" in getattr(msg.channel, "name", "")
    mentioned = client.user in msg.mentions
    if not (is_ask_channel or mentioned):
        return
    question = msg.clean_content.replace("@" + client.user.name, "").strip()
    if not question:
        return
    async with busy:                      # one question at a time
        async with msg.channel.typing():
            try:
                answer = await asyncio.to_thread(
                    ask_claude, question, msg.author.display_name)
            except Exception as e:
                answer = ("The Analyst hit a technical timeout — try that "
                          "one again in a minute. (%s)" % type(e).__name__)
            for i in range(0, len(answer), MAX_DISCORD):
                await msg.reply(answer[i:i + MAX_DISCORD],
                                mention_author=False,
                                allowed_mentions=discord.AllowedMentions.none())


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in tools/ck-desk/.env first "
                         "(see the setup notes at the top of this file).")
    client.run(TOKEN)
