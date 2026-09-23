"""CK Analyst -- the league's interactive content bot.

Listens in Discord and answers league questions within seconds, grounded in
the site's live data: "what happened in the Michigan game?", "predict Ole
Miss vs Oklahoma", "who leads the belt race?".

Triggers only when spoken to directly: an @mention of the bot (user or
role) or a reply to one of its messages. Works in any channel.

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
ROOT = Path(__file__).resolve().parents[2]             # the repo checkout
RAW = "https://raw.githubusercontent.com/spb9876-cmd/campus-kings/main/"
SITE = "https://spb9876-cmd.github.io/campus-kings/"
MAX_DISCORD = 1900                                     # under the 2000 cap
DATA_TTL = 60                                          # local reads are cheap
CAMPUS_ID = 1260753792215810063                        # the league group chat
CHAT_PULL = 40                                         # messages of history per channel
CHAT_CAP = 12000                                       # max chars of chat fed to the model

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
- The RECENT DISCORD CHAT below is ammo: quote the coaches' own words back
  at them (verbatim only, never paraphrased as a quote) and use it to read
  the room, remember what was just said, and keep continuity with your own
  earlier replies. It is banter, not evidence -- if chat contradicts the
  league data, the data wins. Don't repeat slurs or dogpile anyone.
- If asked something outside league scope, deflect with charm in one line.
""" % SITE

_cache = {"at": 0.0, "text": ""}


def grounding():
    """League data blob, refreshed at most every DATA_TTL seconds."""
    import time
    if time.time() - _cache["at"] < DATA_TTL and _cache["text"]:
        return _cache["text"]
    parts = []
    names = ["data/league.json", "docs/search-index.json", "data/content.json"]
    # Current season file, plus last season's for fresh-history questions.
    seasons = sorted((ROOT / "data").glob("season_*.json"))
    if seasons:
        names[1:1] = ["data/" + p.name for p in seasons[-2:]]
    else:
        names.insert(1, "data/season_04.json")   # remote fallback
    # Owner notes carry bracket context (seeds, bowl names, storylines) that
    # the raw results don't -- pull every note file that exists.
    notes = ROOT / "data" / "notes"
    if notes.is_dir():
        names += sorted("data/notes/" + p.name for p in notes.glob("*.md"))
    else:
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
            local = ROOT / name
            if local.is_file():
                # Tier 1 runs on the PC the data is built on: the checkout
                # beats the GitHub CDN, which lags pushes by minutes.
                raw = local.read_text(encoding="utf-8")
            else:
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


def ask_claude(question, asker, chat=""):
    chat_block = ("\n\nRECENT DISCORD CHAT (banter -- quote verbatim, "
                  "newest last):\n%s" % chat) if chat else ""
    prompt = ("%s\n\nLEAGUE DATA (authoritative):\n%s%s\n\n"
              "Coach %s asks: %s\n\nAnswer for Discord:"
              % (HOUSE_RULES, grounding(), chat_block, asker, question))
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


async def chat_context(msg):
    """Recent chat as ammo: the channel the question landed in, plus the
    #campus group chat if that's somewhere else. Bot replies are included
    so the Analyst keeps continuity with what it already said."""

    async def pull(channel):
        lines = []
        try:
            async for m in channel.history(limit=CHAT_PULL):
                text = m.clean_content.strip()
                if not text:
                    continue
                lines.append("%s: %s" % (m.author.display_name, text[:400]))
        except Exception:
            pass
        lines.reverse()                    # oldest first, newest last
        return lines

    parts = ["--- #%s (where the question was asked) ---"
             % getattr(msg.channel, "name", "dm")]
    parts += await pull(msg.channel)
    campus = msg.guild.get_channel(CAMPUS_ID) if msg.guild else None
    if campus and campus.id != msg.channel.id:
        parts.append("--- #campus (the league group chat) ---")
        parts += await pull(campus)
    return "\n".join(parts)[-CHAT_CAP:]


@client.event
async def on_ready():
    print("CK Analyst online as %s (mode: %s)"
          % (client.user, "API" if API_KEY else "Claude subscription"))


def directed_at_bot(msg):
    if client.user in msg.mentions:
        return True
    # Discord auto-creates a role named like the bot; many clients resolve
    # "@CK Analyst" to that role instead of the user. Looks identical in chat.
    me = msg.guild.me if msg.guild else None
    if me and any(r in me.roles for r in msg.role_mentions):
        return True
    ref = getattr(msg.reference, "resolved", None)   # replying to the bot
    return getattr(getattr(ref, "author", None), "id", None) == client.user.id


@client.event
async def on_message(msg):
    if msg.author.bot:
        return
    if not directed_at_bot(msg):
        return
    question = msg.clean_content
    names = {client.user.name}
    if msg.guild and msg.guild.me:
        names.add(msg.guild.me.display_name)
    names.update(r.name for r in msg.role_mentions)
    for n in names:
        question = question.replace("@" + n, "")
    question = question.strip()
    if not question:
        return
    async with busy:                      # one question at a time
        async with msg.channel.typing():
            try:
                chat = await chat_context(msg)
                answer = await asyncio.to_thread(
                    ask_claude, question, msg.author.display_name, chat)
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
