#!/usr/bin/env python3
"""Generate the Campus Kings static site from data/.

    python3 scripts/build.py

Writes docs/*.html and copies media into docs/media/. Everything is derived
from data/ — never edit the generated HTML by hand.
"""
import html
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARTICLES = DATA / "articles"   # long-form write-ups, Markdown
SITE = ROOT / "docs"
MEDIA_SRC = ROOT / "media_src"   # drop new recap PNGs here

sys.path.insert(0, str(Path(__file__).resolve().parent))
from points import (compute, compute_all, completed_seasons, belt_leaders,
                    coach_for, live_bracket, bracket_is_final)
import profiles

# ---------------------------------------------------------------------------
# LOOK AND FEEL -- the "Primetime" system. One design, two palettes.
#
# The site is the broadcast package: the same near-black, championship-gold,
# Anton-numeral house style every published graphic already uses. Night is
# the primary palette; day is the matinee variant of the same design.
# ---------------------------------------------------------------------------

# Palette schedule:
#   "clock"  dark 7pm-7am Eastern, light 7am-7pm, for every visitor regardless
#            of their own timezone or device setting
#   "day"    always the light palette
#   "night"  always the dark palette
SCHEME = "clock"

# Homepage motion: counters rolling up on the belt panel, the 20-season progress
# bar, the newest final flashing in the hero before the ticker, and a one-time
# confetti burst when a season's title game is fresh. False removes every bit of
# it -- no CSS, no JS, no markup hooks -- and all of it already sits behind
# prefers-reduced-motion for visitors who've turned motion off.
MOTION = True

# Gameplay clips behind the homepage hero. Set False to go back to the still
# banner without removing the files.
HERO_VIDEO = True

# Client-side interactivity: sortable tables, the live coach search, the
# archive filter chips, and the manual day/night toggle in the navbar. False
# removes all of it -- markup hooks, CSS and JS -- and the pages read exactly
# as they did before.
DYNAMIC = True

# Where the site is served from. Canonical links, Open Graph URLs and the
# sitemap all need absolute URLs -- crawlers and link unfurlers ignore
# relative ones.
SITE_URL = "https://spb9876-cmd.github.io/campus-kings/"

# Runs synchronously in <head>, before anything paints, so the correct palette is
# in place on the first frame -- set it from a deferred script and every visitor
# after 7pm sees a white flash first. Intl with an IANA zone is used rather than
# a fixed -5 offset so the switch tracks EST/EDT on its own.
CLOCK_JS = """<script>
(function(){
  var root=document.documentElement;
  function easternHour(){
    var h=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',
      hour:'numeric',hour12:false}).format(new Date());
    return parseInt(h,10)%24;           /* some ICU builds say 24 for midnight */
  }
  function apply(){
    /* a manual choice from the navbar toggle beats the clock */
    var s=null; try{s=localStorage.getItem('ck-scheme');}catch(e){}
    if(s==='day'||s==='night'){root.classList.toggle('night',s==='night');return;}
    var h;
    try{h=easternHour();}catch(e){h=new Date().getHours();}  /* no Intl: local */
    root.classList.toggle('night',h>=19||h<7);
  }
  apply();
  window.ckClock=apply;                 /* the toggle re-runs this on "auto" */
  setInterval(apply,60000);             /* flip a page that's been left open */
})();
</script>"""


MOTION_JS = r"""<script>
(function(){
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  /* Reveal-on-scroll: html.rv arms the CSS, so no-JS and reduced-motion
     visitors always see every section without it. */
  document.documentElement.classList.add('rv');
  var rio = new IntersectionObserver(function(es){
    es.forEach(function(e){
      if (e.isIntersecting){ e.target.classList.add('in'); rio.unobserve(e.target); }
    });
  }, {threshold:.1, rootMargin:'0px 0px -30px 0px'});
  document.querySelectorAll('[data-rv]').forEach(function(el){ rio.observe(el); });

  /* Hero clips: play through them in order rather than looping one. */
  var hv = document.querySelector('.herovid');
  if (hv){
    var list = [];
    try { list = JSON.parse(hv.dataset.clips || '[]'); } catch(e){}
    if (list.length > 1){
      hv.removeAttribute('loop');
      /* autoplay would restart the layer every time setClip() reloads it,
         silently burning through the preloaded clip at opacity 0; playback
         is driven explicitly below instead */
      hv.removeAttribute('autoplay');
      var idx = Math.floor(Math.random() * list.length);   /* vary per visit */
      var skips = 0;                     /* cap error-skips so two dead files
                                            can't chase each other forever */
      /* Each entry is the format list for ONE clip. Rebuild the <source>
         children rather than assigning .src, so the browser keeps choosing a
         format it can decode. */
      var setClip = function(v, i){
        v._ci = i;
        v.innerHTML = '';
        var last = null;
        list[i].forEach(function(u){
          var sc = document.createElement('source');
          sc.src = u;
          sc.type = /\.webm$/.test(u) ? 'video/webm' : 'video/mp4';
          v.appendChild(sc);
          last = sc;
        });
        /* the browser fires 'error' on the LAST source when no format worked;
           a clip that can't decode gets skipped instead of wedging the show */
        if (last) last.addEventListener('error', function(){
          if (skips++ > list.length * 2) return;
          setClip(v, (v._ci + 1) % list.length);
          if (v === cur) v.play().catch(function(){});
        });
        v.load();
      };
      /* Second video layer stacked over the first. The next clip preloads in
         whichever layer is hidden and starts playing before the fade, so one
         clip dissolves straight into the next -- neither the poster nor the
         banner still ever shows between highlights. Only the top layer's
         opacity animates; the bottom stays opaque beneath it, so there is no
         half-transparent dip mid-fade. */
      var top = document.createElement('video');
      top.className = 'herovid';
      top.muted = true;
      /* iOS autoplay policy checks the content attributes, not the props */
      top.setAttribute('muted', '');
      top.setAttribute('playsinline', '');
      top.preload = 'auto';
      top.style.opacity = 0;
      hv.parentNode.insertBefore(top, hv.nextSibling);
      var cur = hv, off = top, fading = false;
      setClip(cur, idx);
      cur.play().catch(function(){});
      setClip(off, (idx + 1) % list.length);
      var swap = function(){
        if (fading) return;
        fading = true;
        /* if a background-tab stall let the preloaded clip drift, restart it */
        try { if (off.currentTime > 0) off.currentTime = 0; } catch(e){}
        off.play().catch(function(){});
        top.style.opacity = (off === top) ? 1 : 0;
        setTimeout(function(){
          cur.pause();
          var t = cur; cur = off; off = t;
          /* derive the next preload from what is actually playing, so an
             error-skip above can't desynchronize the rotation */
          setClip(off, (cur._ci + 1) % list.length);
          fading = false;
        }, 850);                        /* just past the .8s opacity fade */
      };
      [cur, off].forEach(function(v){
        /* start the fade shortly before the clip runs out so the motion
           never freezes on a last frame; 'ended' is the no-duration fallback */
        v.addEventListener('timeupdate', function(){
          if (v === cur && !fading && v.duration &&
              v.duration - v.currentTime < 0.9) swap();
        });
        v.addEventListener('ended', function(){
          if (v === cur && !fading) swap();
        });
      });
      /* Hidden tabs pause muted video and throttle timers, which would leave
         the rotation dead when the visitor comes back -- kick it back over. */
      document.addEventListener('visibilitychange', function(){
        if (document.hidden) return;
        if (cur.ended && !fading) swap();
        else cur.play().catch(function(){});
      });
    }
  }

  /* Counters: any element with data-count rolls up from 0 when scrolled in. */
  function roll(el){
    var end = parseFloat(el.dataset.count), dur = 900, t0 = null;
    function step(t){
      if (t0 === null) t0 = t;
      var p = Math.min((t - t0) / dur, 1);
      p = 1 - Math.pow(1 - p, 3);                     /* ease-out cubic */
      el.textContent = Math.round(end * p);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var seen = new WeakSet();
  var io = new IntersectionObserver(function(es){
    es.forEach(function(e){
      if (e.isIntersecting && !seen.has(e.target)){
        seen.add(e.target); roll(e.target); io.unobserve(e.target);
      }
    });
  }, {threshold:.6});
  document.querySelectorAll('[data-count]').forEach(function(el){io.observe(el);});

  /* Belt bar: markup ships pre-lit so no-JS and reduced-motion users see the
     true state; with motion we strip the classes and replay them in sequence. */
  document.querySelectorAll('.beltbar').forEach(function(bar){
    var done = +bar.dataset.done || 0, live = +bar.dataset.live || 0;
    var segs = bar.querySelectorAll('i');
    segs.forEach(function(seg){seg.classList.remove('on','live');});
    segs.forEach(function(seg, i){
      if (i < done) setTimeout(function(){seg.classList.add('on');}, 350 + i*140);
      else if (i < done + live)
        setTimeout(function(){seg.classList.add('live');}, 350 + i*140);
    });
  });

  /* Hero flash: the newest final, big, once per result per browser. */
  var hf = document.querySelector('.heroflash');
  if (hf){
    var key = 'ck-flash-' + hf.dataset.key;
    try {
      if (!localStorage.getItem(key)){
        hf.classList.add('play');
        localStorage.setItem(key, '1');
      }
    } catch(e){ hf.classList.add('play'); }
  }

  /* Champion confetti: only when the newest season's title game is fresh. */
  var pop = document.querySelector('[data-champion]');
  if (pop){
    var ckey = 'ck-champ-' + pop.dataset.champion;
    var fresh = false;
    try { fresh = !localStorage.getItem(ckey); if (fresh) localStorage.setItem(ckey,'1'); }
    catch(e){ fresh = true; }
    if (fresh){
      pop.classList.add('champpop');
      var wrap = document.createElement('div');
      wrap.className = 'confetti';
      var colors = ['#dfa839','#f4f2ea','#9e2b25','#a9863f'];
      for (var i = 0; i < 90; i++){
        var f = document.createElement('i');
        f.style.left = (Math.random()*100) + 'vw';
        f.style.background = colors[i % colors.length];
        f.style.animationDuration = (2.6 + Math.random()*2.4) + 's';
        f.style.animationDelay = (Math.random()*1.4) + 's';
        f.style.transform = 'rotate(' + (Math.random()*360) + 'deg)';
        wrap.appendChild(f);
      }
      document.body.appendChild(wrap);
      setTimeout(function(){ wrap.remove(); }, 6800);
    }
  }
})();
</script>"""

DYNAMIC_JS = r"""<script>
(function(){
  /* ---- theme toggle: cycles auto -> day -> night. "auto" hands control back
     to the 7am/7pm clock in <head>; an explicit choice persists per browser
     and is honoured before first paint by the same head script. ---- */
  var KEY='ck-scheme', root=document.documentElement;
  var btn=document.querySelector('.modebtn');
  function stored(){ try{return localStorage.getItem(KEY);}catch(e){return null;} }
  function paint(){
    var m=stored()||'auto';
    if(m==='day') root.classList.remove('night');
    else if(m==='night') root.classList.add('night');
    if(btn) btn.title={auto:'Theme: automatic (dark 7pm–7am ET) — click for day',
                       day:'Theme: day — click for night',
                       night:'Theme: night — click for automatic'}[m];
  }
  if(btn){
    btn.addEventListener('click',function(){
      var order=['auto','day','night'];
      var next=order[(order.indexOf(stored()||'auto')+1)%3];
      try{ next==='auto'?localStorage.removeItem(KEY):localStorage.setItem(KEY,next); }catch(e){}
      if(next==='auto'&&window.ckClock) window.ckClock();
      paint();
    });
    paint();
  }

  /* ---- sortable tables: click a header to sort, click again to flip.
     Numbers sort numerically ("3-1" and "12 pts" read their leading number,
     blank em-dashes sink to the bottom); everything else sorts as text. ---- */
  document.querySelectorAll('table.sortable').forEach(function(tbl){
    var hrow=tbl.querySelector('tr');
    if(!hrow) return;
    var ths=hrow.querySelectorAll('th');
    function key(tr,ci){
      var td=tr.children[ci];
      var t=td?td.textContent.trim():'';
      var n=parseFloat(t.replace(/[–—].*$/,'').replace(/[^0-9.\-]/g,''));
      return isNaN(n)?t.toLowerCase():n;
    }
    ths.forEach(function(th,ci){
      th.addEventListener('click',function(){
        var rows=[].slice.call(tbl.querySelectorAll('tr')).slice(1);
        var numeric=rows.some(function(r){return typeof key(r,ci)==='number';});
        /* first click: numbers biggest-first, text A-Z; second click flips */
        var dir=th.dataset.dir?(th.dataset.dir==='desc'?'asc':'desc')
                              :(numeric?'desc':'asc');
        ths.forEach(function(t){t.removeAttribute('data-dir');});
        th.dataset.dir=dir;
        rows.sort(function(a,b){
          var ka=key(a,ci),kb=key(b,ci);
          var na=typeof ka==='number',nb=typeof kb==='number';
          /* rows with no value stay below rows with one, whichever way */
          if(na!==nb) return na?-1:1;
          var c=na?ka-kb:(ka<kb?-1:ka>kb?1:0);
          return dir==='asc'?c:-c;
        });
        rows.forEach(function(r){r.parentNode.appendChild(r);});
      });
    });
  });

  /* ---- archive filter + live search. The chips and the search box are one
     filter -- a card shows only when it matches both -- and season sections
     with nothing left disappear rather than leaving a stranded heading. ---- */
  var cards=document.querySelectorAll('.card[data-kind]');
  var chips=document.querySelectorAll('.chip[data-kind]');
  var kind='all', query='';
  function applyCards(){
    cards.forEach(function(card){
      var ok=(kind==='all'||card.dataset.kind===kind)&&
             (!query||card.textContent.toLowerCase().indexOf(query)>-1);
      card.style.display=ok?'':'none';
    });
    document.querySelectorAll('.section').forEach(function(sec){
      var cs=sec.querySelectorAll('.card[data-kind]');
      if(!cs.length) return;
      var any=[].some.call(cs,function(c){return c.style.display!=='none';});
      sec.style.display=any?'':'none';
    });
  }
  chips.forEach(function(ch){
    ch.addEventListener('click',function(){
      chips.forEach(function(c){c.classList.remove('on');});
      ch.classList.add('on');
      kind=ch.dataset.kind;
      applyCards();
    });
  });

  /* ---- live search: any input[data-filter] hides non-matching elements of
     its CSS-selector target as you type. Card targets route through the
     combined filter above so search and chips don't fight. ---- */
  document.querySelectorAll('input[data-filter]').forEach(function(inp){
    var sel=inp.dataset.filter;
    inp.addEventListener('input',function(){
      var q=inp.value.trim().toLowerCase();
      if(cards.length&&sel.indexOf('.card')===0){query=q;applyCards();return;}
      document.querySelectorAll(sel).forEach(function(el){
        el.style.display=!q||el.textContent.toLowerCase().indexOf(q)>-1?'':'none';
      });
    });
  });

  /* ---- site-wide search. The index is one JSON built at generation time --
     coaches, teams, write-ups, and every recorded result -- fetched once on
     first open. "/" or the navbar button opens it; arrows + Enter drive it. ---- */
  var ov=document.querySelector('.searchov');
  if(ov){
    var sbtn=document.querySelector('.searchbtn');
    var sinp=ov.querySelector('.searchinput');
    var sres=ov.querySelector('.searchresults');
    var IX=null, srows=[], scur=-1;
    function sesc(t){return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
    function sload(){
      if(IX) return Promise.resolve(IX);
      return fetch('search-index.json').then(function(r){return r.json();})
        .then(function(j){IX=j;return j;}).catch(function(){IX=[];return IX;});
    }
    function sopen(){ ov.hidden=false; sinp.focus();
      sload().then(function(){srender(sinp.value);}); }
    function sclose(){ ov.hidden=true; sinp.value=''; scur=-1; }
    /* prefix beats word-start beats substring beats subtitle hit */
    function sscore(e,q){
      var t=e.t.toLowerCase(), s=(e.s||'').toLowerCase();
      if(t.indexOf(q)===0) return 0;
      var ws=t.split(/\s+/).some(function(w){return w.indexOf(q)===0;});
      if(ws) return 1;
      if(t.indexOf(q)>-1) return 2;
      if(s.indexOf(q)>-1) return 3;
      return -1;
    }
    function smark(){
      [].forEach.call(sres.children,function(el,i){
        el.classList.toggle('on',i===scur);
      });
      if(scur>-1&&sres.children[scur])
        sres.children[scur].scrollIntoView({block:'nearest'});
    }
    function srender(qraw){
      var q=qraw.trim().toLowerCase();
      if(!q){ sres.innerHTML=''; srows=[]; scur=-1; return; }
      var m=[];
      IX.forEach(function(e){var sc=sscore(e,q); if(sc>-1) m.push([sc,e]);});
      m.sort(function(a,b){return a[0]-b[0];});
      srows=m.slice(0,12).map(function(x){return x[1];});
      scur=srows.length?0:-1;
      sres.innerHTML=srows.map(function(e){
        return '<a class="sr" href="'+sesc(e.h)+'"><span class="sk">'+sesc(e.k)+
               '</span><span class="st">'+sesc(e.t)+'</span><span class="ss">'+
               sesc(e.s||'')+'</span></a>';
      }).join('')||'<div class="snone">No matches</div>';
      smark();
    }
    if(sbtn) sbtn.addEventListener('click',sopen);
    ov.addEventListener('mousedown',function(e){ if(e.target===ov) sclose(); });
    sinp.addEventListener('input',function(){ srender(sinp.value); });
    sinp.addEventListener('keydown',function(e){
      if(e.key==='ArrowDown'){ e.preventDefault();
        if(srows.length){ scur=(scur+1)%srows.length; smark(); } }
      else if(e.key==='ArrowUp'){ e.preventDefault();
        if(srows.length){ scur=(scur-1+srows.length)%srows.length; smark(); } }
      else if(e.key==='Enter'){ if(scur>-1&&srows[scur]) location.href=srows[scur].h; }
      else if(e.key==='Escape') sclose();
    });
    document.addEventListener('keydown',function(e){
      if(!ov.hidden){ if(e.key==='Escape') sclose(); return; }
      var tag=(e.target.tagName||'').toUpperCase();
      if(tag==='INPUT'||tag==='TEXTAREA'||e.target.isContentEditable) return;
      if(e.key==='/'||((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k')){
        e.preventDefault(); sopen();
      }
    });
  }
})();
</script>"""

DYNAMIC_CSS = """
/* ---- interactivity (DYNAMIC = True) ---- */
.modebtn{background:none;border:1px solid var(--rule);border-radius:50%;
  color:var(--muted);width:32px;height:32px;flex:0 0 auto;display:flex;
  align-items:center;justify-content:center;cursor:pointer;padding:0;
  transition:color .15s,border-color .15s}
.modebtn:hover{color:var(--gold);border-color:var(--golddim)}
.modebtn .moon{display:none}
html.night .modebtn .moon{display:block}
html.night .modebtn .sun{display:none}

table.sortable th{cursor:pointer;user-select:none;white-space:nowrap}
table.sortable th:hover{color:var(--gold)}
table.sortable th[data-dir=desc]::after{content:" \\2193";color:var(--gold)}
table.sortable th[data-dir=asc]::after{content:" \\2191";color:var(--gold)}

.searchbar{display:block;width:100%;max-width:360px;margin:0 0 18px;
  padding:10px 14px;font:inherit;font-size:13.5px;color:var(--ink);
  background:var(--card);border:1px solid var(--rule);border-radius:4px;
  transition:border-color .15s}
.searchbar::placeholder{color:var(--muted2)}
.searchbar:focus{outline:none;border-color:var(--gold);box-shadow:0 0 0 3px var(--glow)}

.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.chip{font:inherit;font-size:12px;letter-spacing:.4px;color:var(--muted);
  background:var(--card);border:1px solid var(--rule);border-radius:999px;
  padding:7px 15px;cursor:pointer;transition:color .15s,border-color .15s,background .15s}
.chip:hover{color:var(--ink);border-color:var(--muted)}
.chip.on{color:var(--bg);border-color:var(--gold);font-weight:700;
  background:linear-gradient(135deg,var(--gold2),var(--gold))}
html.night .chip.on{color:#171204}

.searchbtn{background:none;border:1px solid var(--rule);border-radius:50%;
  color:var(--muted);width:32px;height:32px;flex:0 0 auto;display:flex;
  align-items:center;justify-content:center;cursor:pointer;padding:0;
  transition:color .15s,border-color .15s}
.searchbtn:hover{color:var(--gold);border-color:var(--golddim)}
.searchov{position:fixed;inset:0;background:rgba(5,5,8,.68);z-index:90;
  display:flex;align-items:flex-start;justify-content:center;padding:11vh 20px 0}
.searchov[hidden]{display:none}
.searchpanel{width:100%;max-width:600px;background:var(--card);
  border:1px solid var(--golddim);border-radius:8px;overflow:hidden;
  box-shadow:0 24px 80px rgba(0,0,0,.5)}
.searchinput{width:100%;padding:15px 18px;font:inherit;font-size:15px;
  color:var(--ink);background:none;border:none;border-bottom:1px solid var(--rule)}
.searchinput:focus{outline:none}
.searchresults{max-height:52vh;overflow-y:auto}
.sr{display:flex;align-items:baseline;gap:10px;padding:10px 16px;
  border-bottom:1px solid var(--rule);cursor:pointer}
.sr:last-child{border-bottom:none}
.sr.on,.sr:hover{background:var(--card2)}
.sr .sk{font-size:9px;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--gold);flex:0 0 92px}
.sr .st{color:var(--ink);font-size:14px;font-weight:600;white-space:nowrap}
.sr .ss{color:var(--muted);font-size:12px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;min-width:0}
.snone{padding:14px 16px;color:var(--muted);font-size:13px}
.searchhint{padding:8px 16px;font-size:10px;letter-spacing:1px;
  color:var(--muted2);border-top:1px solid var(--rule)}
"""

NIGHT_CLASS = ' class="night"' if SCHEME == "night" else ""
HEAD_JS = CLOCK_JS if SCHEME == "clock" else ""

FONT_QUERY = "family=Anton&family=Inter:wght@400;500;600;700"

NAV = [("index.html", "Home"), ("standings.html", "The Belt"),
       ("coaches.html", "Coaches"), ("records.html", "Records"),
       ("content.html", "Archive"), ("rules.html", "Rulebook"),
       ("history.html", "History")]

_MONTHS = ("Jan", "Feb", "March", "April", "May", "June",
           "July", "Aug", "Sept", "Oct", "Nov", "Dec")


def fmt_date(d):
    """'2026-08-06' -> 'Aug 6, 2026'. Nobody writes ISO dates on a website."""
    try:
        y, m, day = (int(p) for p in str(d).split("-")[:3])
        return "%s %d, %d" % (_MONTHS[m - 1], day, y)
    except (ValueError, IndexError):
        return d

CSS = """
/* ============================================================
   CAMPUS KINGS "PRIMETIME"
   Day tokens on :root, night on html.night -- the 7am/7pm clock
   and the navbar toggle flip that class before first paint.
   ============================================================ */
:root{
  --bg:#f4f0e3; --ink:#171410; --muted:#5d574a; --muted2:#8f8878;
  --gold:#96700f; --gold2:#c2952b; --golddim:#7a5a0e;
  --rule:#ded5bd; --card:#fbf7ec; --card2:#ebe5d2; --turf:#e9e3d0;
  --nav:rgba(244,240,227,.97);
  --onphoto:#f6f3e8; --onphoto-dim:rgba(246,243,232,.84);
  --onphoto-accent:#f0c65e;
  --glow:rgba(150,112,15,.10);
  --shadow:0 22px 60px rgba(23,20,16,.14);
  --display:'Anton',Impact,'Arial Narrow',sans-serif;
}
html.night{
  --bg:#08080b; --ink:#f4f1e6; --muted:#a09a8c; --muted2:#645f53;
  --gold:#dfa839; --gold2:#f2cd6f; --golddim:#a9863f;
  --rule:#232017; --card:#0f0f13; --card2:#16161b; --turf:#0d1410;
  --nav:rgba(8,8,11,.96);
  --onphoto-accent:#f2cd6f;
  --glow:rgba(223,168,57,.14);
  --shadow:0 26px 70px rgba(0,0,0,.55);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg)}
body{font-family:'Inter',system-ui,sans-serif;font-size:15px;color:var(--ink);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit;text-decoration:none}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px;border-radius:2px}
::selection{background:var(--gold);color:var(--bg)}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
.skip{position:absolute;left:-9999px;top:0;z-index:200;background:var(--gold);
  color:#0a0a0c;padding:10px 18px;font-weight:700;font-size:13px}
.skip:focus{left:0}

/* No backdrop-filter here: blurring the page beneath a sticky bar froze the
   renderer outright on scroll (reproduced in two browsers). A near-opaque
   background reads the same at none of the cost. */
.navbar{position:sticky;top:0;z-index:40;background:var(--nav)}
.navbar::after{content:"";display:block;height:2px;background:
  linear-gradient(90deg,transparent,var(--gold) 15%,var(--gold2) 50%,var(--gold) 85%,transparent)}
.navbar .inner{max-width:1080px;margin:0 auto;padding:14px 24px;display:flex;
  align-items:center;justify-content:space-between;gap:16px}
.navside{display:flex;align-items:center;gap:15px;min-width:0;flex:0 1 auto}
.brand{display:flex;align-items:center;gap:11px;flex:0 0 auto}
.brand .name{white-space:nowrap}
.brand .mark{width:32px;height:32px;display:block;border-radius:50%;
  box-shadow:0 0 0 1px var(--rule),0 0 18px var(--glow)}
.brand .name{font-family:var(--display);font-size:19px;letter-spacing:2px;text-transform:uppercase}
.brand .name span{color:var(--gold)}
nav{display:flex;gap:19px;font-size:11.5px;letter-spacing:1.8px;text-transform:uppercase;color:var(--muted)}
nav a{padding:5px 0;border-bottom:2px solid transparent;transition:color .15s}
nav a:hover{color:var(--ink)}
nav a.on{color:var(--gold);border-bottom-color:var(--gold)}

.hero{position:relative;overflow:hidden;border-bottom:1px solid var(--rule);
  background:var(--turf)}
/* layer 1 - the photo. cover fills the box, center keeps the crest in frame */
.hero .banner{position:absolute;inset:-20px;background:url('media/hero-banner.jpg') center/cover no-repeat;
  /* blur kills the banner's own lettering so it can't compete with our headline;
     inset:-20px hides the soft edge the blur creates */
  filter:blur(7px) saturate(1.05)}
/* layer 2 - the scrim. without this the text is unreadable over the photo */
.hero .scrim{position:absolute;inset:0;background:
  linear-gradient(180deg,rgba(6,6,9,.62) 0%,rgba(6,6,9,.52) 42%,
    rgba(6,6,9,.80) 80%,var(--bg) 100%),
  radial-gradient(ellipse 900px 420px at 50% 0%,rgba(223,168,57,.20),transparent 70%)}
/* text hugs the top of the box; the fat bottom pad keeps the hero tall so the
   gameplay clip stays in view under the headline */
.hero .inner{position:relative;z-index:2;max-width:1080px;margin:0 auto;
  padding:64px 24px 230px;text-align:center}
/* only the homepage hero sits on the dark photo/video; the coach and article
   heroes have no .banner and keep page-colored text */
.hero .banner ~ .inner{color:var(--onphoto)}
.hero .banner ~ .inner h1{text-shadow:0 4px 44px rgba(0,0,0,.55)}
.hero .crest{width:118px;height:118px;display:block;margin:0 auto 22px;border-radius:50%;
  box-shadow:0 0 44px rgba(223,168,57,.22)}
.scrollcue{display:flex;flex-direction:column;align-items:center;gap:7px;margin-top:30px;
  font-size:10px;letter-spacing:2.6px;text-transform:uppercase;color:rgba(246,243,232,.55)}
.scrollcue svg{animation:bob 1.9s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(4px)}}
@media(prefers-reduced-motion:reduce){.scrollcue svg{animation:none}}
.quick{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:1px;
  background:var(--rule);border-bottom:1px solid var(--rule)}
.quick a{background:var(--card);padding:20px 22px;display:block;position:relative;
  overflow:hidden;transition:background .2s}
.quick a::after{content:"";position:absolute;left:0;top:0;bottom:0;width:0;
  background:linear-gradient(180deg,var(--gold2),var(--gold));transition:width .2s}
.quick a:hover{background:var(--card2)}
.quick a:hover::after{width:3px}
.quick .qk{font-family:var(--display);font-size:15px;text-transform:uppercase;
  letter-spacing:1.4px;margin-bottom:4px}
.quick .qd{font-size:11.5px;color:var(--muted);line-height:1.5}
.quick .qk span{color:var(--gold);display:inline-block;transition:transform .2s}
.quick a:hover .qk span{transform:translateX(4px)}
.eyebrow{font-size:11px;letter-spacing:3.5px;text-transform:uppercase;color:var(--gold);font-weight:700}
.hero .banner ~ .inner .eyebrow{display:inline-flex;align-items:center;gap:10px;
  color:var(--onphoto-accent);border:1px solid rgba(240,198,94,.38);border-radius:999px;
  padding:8px 18px;background:rgba(6,6,9,.42)}
.hero h1{font-family:var(--display);font-size:clamp(46px,7.4vw,94px);line-height:.94;
  text-transform:uppercase;margin:24px 0 0;letter-spacing:1px}
.hero h1 em{font-style:normal;color:#e9b545}
.stinger{display:inline-flex;align-items:center;gap:12px;margin-top:26px;padding:10px 20px;
  background:rgba(6,6,9,.6);border:1px solid rgba(240,198,94,.45);border-radius:3px;
  font-size:12px;letter-spacing:2.4px;text-transform:uppercase;color:var(--onphoto)}
.stinger b{color:var(--onphoto-accent);font-weight:700}
.stinger .sep{color:rgba(246,243,232,.4)}
.hero p.lede{max-width:640px;margin:18px auto 0;color:var(--muted);font-size:15.5px;line-height:1.65}
.hero .banner ~ .inner .lede{color:var(--onphoto-dim)}
.btn{font-size:12px;letter-spacing:1.6px;text-transform:uppercase;padding:11px 22px;
  border:1px solid var(--golddim);color:var(--gold);border-radius:2px;transition:.15s}
.btn:hover{background:var(--gold);color:var(--bg)}

.glance{border-bottom:1px solid var(--rule);background:var(--card)}
.glance .inner{max-width:1080px;margin:0 auto;padding:0 24px;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
.glance .cell{padding:26px 8px;text-align:center;border-left:1px solid var(--rule)}
.glance .cell:first-child{border-left:none}
.glance .fig{font-family:var(--display);font-size:36px;line-height:1;color:var(--gold)}
.glance .lab{font-size:10.5px;letter-spacing:2.2px;text-transform:uppercase;color:var(--muted2);margin-top:9px}

.section{padding:64px 0;border-bottom:1px solid var(--rule)}
.section:last-of-type{border-bottom:none}
h2.sec{display:flex;align-items:center;gap:12px;font-size:11px;letter-spacing:3.4px;
  font-weight:700;color:var(--muted);text-transform:uppercase;margin:0 0 26px}
h2.sec::before{content:"";width:24px;height:11px;flex:0 0 auto;
  background:linear-gradient(135deg,var(--gold2),var(--gold));
  transform:skewX(-16deg)}
h2.sec::after{content:"";flex:1;height:1px;background:var(--rule)}
h1.page{font-family:var(--display);font-size:clamp(38px,6vw,64px);line-height:.98;
  text-transform:uppercase;margin:0 0 14px;letter-spacing:1px}
h1.page em{font-style:normal;color:var(--gold)}
.psub{color:var(--muted);font-size:15.5px;margin:0;line-height:1.65;max-width:720px}
.pagehead{padding:60px 0 38px;border-bottom:1px solid var(--rule);position:relative}
.pagehead::before{content:"";position:absolute;left:-24px;right:-24px;top:0;bottom:0;
  background:radial-gradient(ellipse 640px 200px at 18% 0%,var(--glow),transparent 70%);
  pointer-events:none}

.secintro{color:var(--muted);font-size:16px;line-height:1.7;max-width:740px;margin:-6px 0 28px}
.pillars{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1px;background:var(--rule)}
.pillar{background:var(--card);padding:28px 26px;position:relative;overflow:hidden}
.pillar .n{font-family:var(--display);font-size:44px;line-height:1;color:transparent;
  -webkit-text-stroke:1px var(--golddim);opacity:.55;position:absolute;right:16px;top:12px}
.pillar h3{font-size:16px;margin:0 0 9px;letter-spacing:.2px;padding-right:52px}
.pillar p{margin:0;font-size:13.5px;color:var(--muted);line-height:1.62}

.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px}
.step{border-top:2px solid var(--golddim);padding-top:16px}
.step .k{font-family:var(--display);font-size:15px;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:7px}
.step p{margin:0;font-size:13px;color:var(--muted);line-height:1.6}

.belt{position:relative;overflow:hidden;background:linear-gradient(160deg,var(--card2),var(--card));
  border:1px solid var(--rule);border-radius:6px;padding:28px 30px}
.belt::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;
  background:linear-gradient(90deg,var(--golddim),var(--gold2) 40%,var(--gold) 70%,var(--golddim))}
.belt::after{content:"";position:absolute;right:-70px;top:-70px;width:260px;height:260px;
  border-radius:50%;background:radial-gradient(circle,var(--glow),transparent 70%);pointer-events:none}
.belt .lbl{font-size:10.5px;letter-spacing:2.8px;color:var(--gold);text-transform:uppercase;font-weight:700}
.belt .who{font-family:var(--display);font-size:clamp(28px,4vw,42px);margin:10px 0 6px;
  text-transform:uppercase;letter-spacing:.5px;line-height:1.02}
.belt .meta{font-size:13px;color:var(--muted);line-height:1.65;max-width:600px}

.row{position:relative;display:flex;align-items:center;gap:18px;padding:14px 18px;
  margin-bottom:8px;background:var(--card);border:1px solid var(--rule);border-radius:5px;
  overflow:hidden;transition:border-color .15s}
.row:hover{border-color:var(--golddim)}
.row .ptbar{position:absolute;left:0;top:0;bottom:0;width:var(--w,0%);
  background:linear-gradient(90deg,var(--glow),transparent);pointer-events:none}
.row.lead{border-color:var(--golddim)}
.num{font-family:var(--display);font-size:24px;color:var(--gold);width:40px;flex-shrink:0;line-height:1.1}
.bd{flex:1;min-width:0;position:relative}
.tm{font-size:15px;font-weight:700}
.co{font-size:11px;color:var(--muted2);text-transform:uppercase;letter-spacing:.6px;margin-left:8px}
.dt{font-size:12.5px;color:var(--muted);margin-top:4px;line-height:1.5}
.rt{font-family:var(--display);font-size:19px;color:var(--ink);flex-shrink:0;
  white-space:nowrap;position:relative}
.rt small{font-size:10px;letter-spacing:1.6px;color:var(--muted2);font-family:'Inter',sans-serif;
  text-transform:uppercase;margin-left:5px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:10.5px;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--muted2);font-weight:700;padding:0 10px 10px 0;border-bottom:2px solid var(--rule)}
td{padding:12px 10px 12px 0;border-bottom:1px solid var(--rule)}
tr:hover td{background:var(--glow)}
td.w{font-weight:700}
td.s{font-family:var(--display);color:var(--gold);white-space:nowrap;letter-spacing:.5px}
a.clink{color:inherit;border-bottom:1px dotted var(--muted2);transition:color .12s,border-color .12s}
a.clink:hover{color:var(--gold);border-bottom-color:var(--gold)}
.tm a.clink{border-bottom-color:var(--rule)}
.tag{font-size:9.5px;letter-spacing:1px;text-transform:uppercase;color:var(--golddim);
  border:1px solid var(--rule);border-radius:2px;padding:2px 6px;margin-left:8px;white-space:nowrap}
.wklabel{font-family:var(--display);font-size:13px;color:var(--gold);letter-spacing:2px;
  text-transform:uppercase;margin:26px 0 8px}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--rule);border-radius:6px;overflow:hidden;
  display:block;transition:border-color .2s,transform .2s,box-shadow .2s}
.card:hover{border-color:var(--golddim);transform:translateY(-3px);box-shadow:var(--shadow)}
.card img{width:100%;display:block;height:150px;object-fit:cover;object-position:top;
  border-bottom:1px solid var(--rule);transition:transform .4s ease}
.card:hover img{transform:scale(1.045)}
.card .body{padding:15px 17px}
.card .kind{font-size:10px;letter-spacing:2px;color:var(--gold);font-weight:700;text-transform:uppercase}
.card .ttl{font-size:14.5px;font-weight:700;margin:7px 0 5px;line-height:1.35}
.card .bl{font-size:12.5px;color:var(--muted);line-height:1.55}
.card .dte{font-size:10.5px;color:var(--muted2);margin-top:10px;letter-spacing:.5px}

/* ---- the throne: reigning champ + belt race, side by side ---- */
.throne{display:grid;grid-template-columns:1.15fr 1fr;gap:16px}
.race{display:flex;gap:30px;margin:16px 0 4px;flex-wrap:wrap}
.race .rc .n{font-family:var(--display);font-size:46px;line-height:1;color:var(--gold)}
.race .rc .w{font-size:12px;font-weight:700;margin-top:5px}
.race .rc .w a{border-bottom:1px dotted var(--muted2)}
.race .rc .w a:hover{color:var(--gold);border-bottom-color:var(--gold)}
.dynasty{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
.dyn{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--rule);
  border-radius:4px;padding:10px 14px;font-size:12.5px;transition:border-color .15s}
.dyn:hover{border-color:var(--golddim)}
.dyn .s{font-family:var(--display);color:var(--gold);font-size:14px;letter-spacing:1px}
.dyn b{font-weight:700}
.dyn .c{color:var(--muted)}

/* ---- record book ---- */
.recgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));gap:14px}
.rec{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:20px 22px;
  position:relative;overflow:hidden;transition:border-color .2s,transform .2s}
.rec:hover{border-color:var(--golddim);transform:translateY(-2px)}
.rec::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
  background:linear-gradient(180deg,var(--gold2),var(--golddim))}
.rec .k{font-size:10px;letter-spacing:2.2px;text-transform:uppercase;color:var(--gold);font-weight:700}
.rec .v{font-family:var(--display);font-size:24px;margin:9px 0 5px;text-transform:uppercase;line-height:1.08}
.rec .d{font-size:12.5px;color:var(--muted);line-height:1.55}

/* ---- coach cards + dossier ---- */
.coachgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(236px,1fr));gap:14px}
.ccard{display:block;background:var(--card);border:1px solid var(--rule);border-radius:6px;
  padding:22px;position:relative;overflow:hidden;
  transition:transform .2s,border-color .2s,box-shadow .2s}
.ccard:hover{transform:translateY(-3px);border-color:var(--golddim);box-shadow:var(--shadow)}
.ccard::before{content:"";position:absolute;left:0;right:0;top:0;height:2px;
  background:linear-gradient(90deg,var(--golddim),var(--gold2),var(--golddim));
  opacity:0;transition:opacity .2s}
.ccard:hover::before{opacity:1}
.ccard .nm{font-family:var(--display);font-size:23px;text-transform:uppercase;letter-spacing:.5px}
.ccard .tmm{color:var(--muted);font-size:13px;margin-top:4px}
.ccard .line{display:flex;gap:16px;margin-top:14px;font-size:11.5px;color:var(--muted2);
  letter-spacing:.4px}
.ccard .line b{color:var(--ink);font-weight:700}
.ringrow{display:flex;gap:5px;margin-top:13px;min-height:14px}
.ring{width:14px;height:14px;border-radius:50%;border:1.5px solid var(--gold);
  background:radial-gradient(circle at 35% 30%,var(--gold2),var(--golddim));
  box-shadow:0 0 8px var(--glow)}
.form{display:inline-flex;gap:4px;vertical-align:middle}
.form i{width:9px;height:9px;border-radius:2px;background:var(--rule)}
.form i.w{background:var(--gold)}
.form i.l{background:var(--muted2);opacity:.55}

/* --- long-form write-ups --- */
.poster{display:block;margin:0 0 40px;border:1px solid var(--rule);border-radius:6px;overflow:hidden;
  transition:border-color .2s,box-shadow .2s}
.poster:hover{border-color:var(--golddim);box-shadow:var(--shadow)}
.poster img{width:100%;display:block}
.poster .cap{padding:11px 15px;font-size:10.5px;letter-spacing:1.8px;text-transform:uppercase;
  color:var(--muted2);border-top:1px solid var(--rule);background:var(--card)}
.poster:hover .cap{color:var(--gold)}
.article{max-width:680px}
.article h2{font-family:var(--display);font-size:26px;text-transform:uppercase;
  letter-spacing:.8px;margin:44px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--rule)}
.article h3{font-size:16.5px;font-weight:700;letter-spacing:.2px;margin:30px 0 12px;color:var(--gold)}
.article p{font-size:15.5px;color:var(--muted);line-height:1.8;margin:0 0 18px}
.article strong{color:var(--ink);font-weight:700}
.article em{color:var(--ink);font-style:italic}
.article a{color:var(--gold);border-bottom:1px dotted var(--golddim)}
.article ul{margin:0 0 18px;padding-left:0;list-style:none}
.article li{position:relative;padding:7px 0 7px 20px;font-size:14px;color:var(--muted);line-height:1.7}
.article li::before{content:"";position:absolute;left:0;top:15px;width:6px;height:6px;
  background:linear-gradient(135deg,var(--gold2),var(--golddim));border-radius:1px}
.article li strong{color:var(--ink)}
.article hr{border:none;border-top:1px solid var(--rule);margin:36px 0}
.article > *:first-child{margin-top:0}
.byline{font-size:11px;letter-spacing:2.4px;text-transform:uppercase;color:var(--muted2);
  margin:0 0 34px;padding-bottom:16px;border-bottom:1px solid var(--rule)}
.backlink{padding-top:34px;margin-top:34px;border-top:1px solid var(--rule);font-size:13px}
.backlink a{color:var(--gold)}

.rulegrid{display:grid;grid-template-columns:210px 1fr;gap:44px;align-items:start}
.toc{position:sticky;top:88px;font-size:12.5px}
.toc a{display:block;padding:7px 0 7px 12px;color:var(--muted);border-left:2px solid var(--rule);line-height:1.4;
  transition:color .15s,border-color .15s}
.toc a:hover{color:var(--gold);border-left-color:var(--gold)}
.rule{padding:0 0 34px;margin-bottom:34px;border-bottom:1px solid var(--rule)}
.rule:last-child{border-bottom:none;margin-bottom:0}
.rule h3{font-family:var(--display);font-size:22px;text-transform:uppercase;
  letter-spacing:.8px;margin:0 0 14px;scroll-margin-top:100px}
.rule p{font-size:14px;color:var(--muted);line-height:1.7;margin:0 0 14px}
.rule ul{margin:0 0 14px;padding-left:0;list-style:none}
.rule li{position:relative;padding:8px 0 8px 20px;font-size:13.5px;color:var(--ink);
  line-height:1.6;border-bottom:1px solid var(--rule)}
.rule li:last-child{border-bottom:none}
.rule li::before{content:"";position:absolute;left:0;top:15px;width:7px;height:7px;
  background:linear-gradient(135deg,var(--gold2),var(--golddim));border-radius:1px}
.flag{background:var(--glow);border:1px solid var(--golddim);border-radius:4px;
  padding:12px 15px;font-size:12.5px;color:var(--gold);margin-bottom:16px;line-height:1.55;font-weight:600}
.foot-note{font-size:12.5px;color:var(--muted2);line-height:1.65;font-style:italic;margin:14px 0 0}
.rt-tables{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:20px;margin-bottom:16px}

footer{border-top:1px solid var(--rule);padding:40px 0 48px;text-align:center;position:relative}
footer::before{content:"";position:absolute;left:0;right:0;top:-1px;height:1px;
  background:linear-gradient(90deg,transparent,var(--golddim),transparent)}
footer .fbrand{font-family:var(--display);font-size:18px;letter-spacing:2.4px;text-transform:uppercase}
footer .fbrand span{color:var(--gold)}
footer .fnav{display:flex;gap:8px 20px;justify-content:center;flex-wrap:wrap;margin:16px 0 12px;
  font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
footer .fnav a:hover{color:var(--gold)}
footer .fnote{font-size:10.5px;color:var(--muted2);letter-spacing:1.6px;text-transform:uppercase;line-height:1.9}

.ticker{position:relative;overflow:hidden;background:var(--card);border-bottom:1px solid var(--rule);
  height:46px;display:flex;align-items:center}
.ticker::before{content:"Latest";position:absolute;left:0;top:0;bottom:0;z-index:3;
  display:flex;align-items:center;padding:0 24px 0 15px;color:#171204;
  font-family:var(--display);font-size:12px;letter-spacing:2.2px;text-transform:uppercase;
  /* the angled trailing edge is a gradient hard-stop, not a clip-path */
  background:linear-gradient(102deg,var(--gold2),var(--gold) 55%,
    var(--gold) calc(100% - 14px),transparent calc(100% - 13px))}
.ticker::after{content:"";position:absolute;right:0;top:0;bottom:0;width:70px;z-index:2;
  background:linear-gradient(90deg,transparent,var(--card));pointer-events:none}
.ticker .track{display:flex;align-items:center;gap:0;white-space:nowrap;
  padding-left:104px;animation:slide 52s linear infinite;will-change:transform}
.ticker:hover .track{animation-play-state:paused}
@keyframes slide{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.tk{display:inline-flex;align-items:center;gap:9px;padding:0 20px;font-size:12.5px;
  border-right:1px solid var(--rule)}
.tk .wk{font-size:9.5px;letter-spacing:1.4px;color:var(--muted2);text-transform:uppercase;font-weight:700}
.tk .a{font-weight:700}
.tk .b{color:var(--muted)}
.tk .sc{font-family:var(--display);color:var(--gold);letter-spacing:.5px;font-size:14px}
.tk .gw{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:#171204;font-weight:700;
  background:linear-gradient(135deg,var(--gold2),var(--gold));border-radius:2px;padding:2px 6px}
@media(prefers-reduced-motion:reduce){.ticker .track{animation:none}}


@media(max-width:1120px){
  nav{gap:13px;font-size:11px;letter-spacing:1.2px}
  .brand .name{font-size:17px;letter-spacing:1.2px}}
@media(max-width:940px){
  nav{overflow-x:auto;-webkit-overflow-scrolling:touch;min-width:0;
    scrollbar-width:none;padding-bottom:2px}
  nav::-webkit-scrollbar{display:none}
  nav a{white-space:nowrap;flex:0 0 auto}}
@media(max-width:820px){.throne{grid-template-columns:1fr}}
@media(max-width:720px){.rulegrid{grid-template-columns:1fr}.toc{display:none}
  /* tiebreaker columns are reference detail; drop them rather than let the
     table push the whole page sideways on a phone */
  .tb{display:none}
  /* seven nav items don't fit at 390px. Let the nav scroll on its own
     instead of widening the document. */
  .navbar .inner{gap:10px}
  nav{gap:14px;font-size:11px;letter-spacing:1px;overflow-x:auto;
    -webkit-overflow-scrolling:touch;max-width:100%;
    scrollbar-width:none;padding-bottom:2px}
  nav::-webkit-scrollbar{display:none}
  nav a{white-space:nowrap;flex:0 0 auto}
  .brand .name{font-size:14px;letter-spacing:1px;white-space:nowrap}
  .brand .mark{width:26px;height:26px}
  .hero .inner{padding:52px 20px 190px}
  .section{padding:48px 0}}
.section{overflow-x:auto}
"""

HERO_CSS = """
/* ---- hero gameplay video ---- */
.hero .herovid{position:absolute;inset:-2px;width:calc(100% + 4px);
  height:calc(100% + 4px);object-fit:cover;z-index:0;
  /* the banner still sits underneath as the paint-first layer */
  filter:saturate(.92) contrast(1.04) brightness(.86);
  /* the second JS-made layer crossfades clip-to-clip via inline opacity */
  transition:opacity .8s ease}
.hero .scrim{z-index:1}
.hero .inner{position:relative;z-index:2}
@media(prefers-reduced-motion:reduce){
  /* poster only -- never autoplay motion at someone who asked us not to */
  .hero .herovid{display:none}
}
"""

if HERO_VIDEO:
    CSS = CSS + HERO_CSS

MOTION_CSS = """
/* ---- homepage motion (MOTION = True) ---- */
.beltbar{display:flex;gap:4px;margin-top:16px}
.beltbar i{flex:1;height:6px;background:var(--rule);border-radius:1px;
  transition:background .4s ease}
.beltbar i.on{background:linear-gradient(180deg,var(--gold2),var(--gold))}
.beltbar i.live{background:var(--golddim);opacity:.65}
.beltbar-lab{font-size:10px;letter-spacing:1.6px;color:var(--muted2);margin-top:8px}

/* sections fade up as they enter; html.rv is set by JS, so no-JS and
   reduced-motion visitors always see everything */
html.rv [data-rv]{opacity:0;transform:translateY(16px);
  transition:opacity .55s ease,transform .55s ease}
html.rv [data-rv].in{opacity:1;transform:none}

.heroflash{position:absolute;left:0;right:0;bottom:26px;text-align:center;
  opacity:0;pointer-events:none;z-index:3}
.heroflash .in{display:inline-block;padding:10px 22px;background:rgba(10,10,12,.82);
  border:1px solid var(--golddim);border-radius:2px}
.heroflash .fw{font-family:'Anton','DejaVu Sans Condensed',Impact,sans-serif;
  font-size:22px;letter-spacing:.5px;color:#f4f2ea;text-transform:uppercase}
.heroflash .fs{color:var(--gold);margin:0 10px}
.heroflash .fl{display:block;color:#8d8b82;font-size:10px;
  letter-spacing:2px;text-transform:uppercase;margin-top:6px}
.heroflash .fk{display:block;font-size:9px;letter-spacing:2.6px;color:var(--gold);
  margin-bottom:5px;text-transform:uppercase}
.heroflash.play{animation:flashin 3.4s ease forwards}
@keyframes flashin{0%{opacity:0;transform:translateY(14px)}
  8%{opacity:1;transform:translateY(0)}78%{opacity:1}100%{opacity:0}}

.confetti{position:fixed;inset:0;pointer-events:none;z-index:60;overflow:hidden}
.confetti i{position:absolute;top:-14px;width:7px;height:11px;opacity:.9;
  animation:cfall linear forwards}
@keyframes cfall{to{transform:translateY(105vh) rotate(660deg);opacity:.15}}
.champpop{animation:champin 1.1s cubic-bezier(.16,1.2,.3,1) both}
@keyframes champin{0%{opacity:0;transform:scale(.82)}100%{opacity:1;transform:scale(1)}}

@media(prefers-reduced-motion:reduce){
  .heroflash{display:none}
  .confetti{display:none}
  .champpop{animation:none}
  .beltbar i{transition:none}
}
"""

if MOTION:
    CSS = CSS + MOTION_CSS

if DYNAMIC:
    CSS = CSS + DYNAMIC_CSS

CROWN = '<img class="mark" src="media/logo-mark.png" alt="">' 

PO_ORDER = {"R1": 0, "QF": 1, "SF": 2, "NC": 3}


def ticker(season_data, limit=14):
    """Scrolling scorebug of the most recent results.

    Postseason outranks the regular season, and deeper rounds outrank earlier
    ones, so the ticker leads with the biggest game the league has played rather
    than whatever happened in the last regular week.

    The item list is emitted twice so the CSS translateX(-50%) loop is seamless.
    """
    # (sort key, chip label, winner, score, loser, trailing tag)
    entries = []

    for r in season_data.get("results", []):
        entries.append(((0, r["week"]), "W%s" % r["week"], r["winner"],
                        r.get("score"), r["loser"],
                        profiles.exempt_tag(r)
                        or ("GOTW" if r.get("gotw") else "")))

    for cc in season_data.get("conference_championships") or []:
        entries.append(((1, 0), cc["conference"], cc["winner"],
                        cc.get("score"), cc["loser"],
                        profiles.exempt_tag(cc) or "CONF"))

    for bg in season_data.get("bowls") or []:
        entries.append(((1, 0), bg.get("bowl", "Bowl"), bg["winner"],
                        bg.get("score"), bg["loser"],
                        profiles.exempt_tag(bg) or "BOWL"))

    for g in season_data.get("playoffs") or []:
        rnd = g.get("round")
        tag = (profiles.exempt_tag(g)
               or ("TITLE" if rnd == "NC" else (g.get("bowl") or "")))
        entries.append(((2, PO_ORDER.get(rnd, 0)), rnd or "PO", g["winner"],
                        g.get("score"), g["loser"], tag))

    if not entries:
        return ""
    entries.sort(key=lambda e: e[0], reverse=True)

    items = []
    for _, label, winner, score, loser, tag in entries[:limit]:
        sc = "%d&ndash;%d" % tuple(score) if score else "TBD"
        chip = '<span class="gw">%s</span>' % tag if tag else ""
        items.append(
            f'<span class="tk"><span class="wk">{label}</span>'
            f'<span class="a">{winner}</span>'
            f'<span class="sc">{sc}</span>'
            f'<span class="b">{loser}</span>{chip}</span>'
        )
    strip = "".join(items)
    return f'<div class="ticker"><div class="track">{strip}{strip}</div></div>'


SEARCH_BTN = """<button class="searchbtn" type="button" aria-label="Search the site" title="Search (press /)">
<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
</button>"""

SEARCH_OV = """<div class="searchov" hidden><div class="searchpanel">
<input class="searchinput" type="search" placeholder="Search coaches, teams, results, content&hellip;" aria-label="Search the site" autocomplete="off">
<div class="searchresults"></div>
<div class="searchhint">&uarr;&darr; to navigate &middot; Enter to open &middot; Esc to close</div>
</div></div>"""

MODE_BTN = """<button class="modebtn" type="button" aria-label="Switch color scheme">
<svg class="sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
<svg class="moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
</button>"""


def shell(title, active, body, hero=None, bug="", desc=None, path=None):
    nav = ""
    for href, label in NAV:
        on = " class='on'" if href == active else ""
        nav += "<a href='%s'%s>%s</a>" % (href, on, label)
    desc = html.escape(desc or "Campus Kings — a 20-season CFB 27 online "
                       "dynasty league. One belt.", quote=True)
    page = path or active
    canonical = SITE_URL + ("" if page == "index.html" else page)
    mode_btn = MODE_BTN if DYNAMIC else ""
    search_ui = (SEARCH_BTN, SEARCH_OV) if DYNAMIC else ("", "")
    fnav = "".join("<a href='%s'>%s</a>" % (href, label) for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en"{NIGHT_CLASS}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{HEAD_JS}
<title>{title} — Campus Kings</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{html.escape(title, quote=True)} — Campus Kings">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE_URL}media/logo.png">
<meta name="twitter:card" content="summary">
<link rel="icon" href="media/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?{FONT_QUERY}&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a>
<div class="navbar"><div class="inner">
<a class="brand" href="index.html">{CROWN}<span class="name">Campus <span>Kings</span></span></a>
<div class="navside"><nav>{nav}</nav>{search_ui[0]}{mode_btn}</div></div></div>
{search_ui[1]}
{bug}
{hero or ""}
<div class="wrap" id="main">{body}</div>
<footer><div class="fbrand">Campus <span>Kings</span></div>
<div class="fnav">{fnav}</div>
<div class="fnote">CFB 27 online dynasty &middot; twenty seasons &middot; one belt<br>
Updated {fmt_date(date.today().isoformat())}</div></footer>
{MOTION_JS if MOTION else ""}{DYNAMIC_JS if DYNAMIC else ""}</body></html>
"""


def load(n):
    return json.loads((DATA / n).read_text(encoding="utf-8"))


def slug(text):
    """URL-safe stem for an article page: 'Weeks 8-10 Recap' -> 'weeks-8-10-recap'."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return s.strip("-")


def _inline(t):
    """Bold, italic, code and links inside a line of prose. HTML is escaped first."""
    t = html.escape(t, quote=False)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def markdown(text):
    """Render the small Markdown subset the write-ups actually use.

    Supported: ## and ### headings, --- rules, - bullet lists, blank-line
    paragraphs, and inline bold / italic / code / links. Deliberately not a
    full parser — anything fancier should be written as plain paragraphs.
    """
    out, para, items = [], [], []

    def flush_para():
        if para:
            out.append("<p>%s</p>" % _inline(" ".join(para)))
            para.clear()

    def flush_list():
        if items:
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _inline(i) for i in items))
            items.clear()

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_para()
            flush_list()
        elif stripped.startswith("### "):
            flush_para(); flush_list()
            out.append("<h3>%s</h3>" % _inline(stripped[4:]))
        elif stripped.startswith("## "):
            flush_para(); flush_list()
            out.append("<h2>%s</h2>" % _inline(stripped[3:]))
        elif stripped.startswith("# "):
            flush_para(); flush_list()
            out.append("<h2>%s</h2>" % _inline(stripped[2:]))
        elif set(stripped) == {"-"} and len(stripped) >= 3:
            flush_para(); flush_list()
            out.append("<hr>")
        elif stripped.startswith("- "):
            flush_para()
            items.append(stripped[2:])
        elif items and raw.startswith("  "):
            items[-1] += " " + stripped        # continuation of the last bullet
        else:
            flush_list()
            para.append(stripped)

    flush_para()
    flush_list()
    return "\n".join(out)


def article_path(entry):
    """The page this manifest entry links to: its write-up if it has one, else the raw image."""
    if entry.get("article"):
        return "post-%s.html" % slug(entry.get("slug") or entry["title"])
    return "media/%s" % entry["file"]


def entry_images(entry):
    """Every image the article body should show, as (file, caption) pairs.

    An entry's "file" is always the card thumbnail. Add a "gallery" to show more
    than one graphic in the write-up -- either bare filenames or
    {"file": ..., "caption": ...} objects. Without a gallery, the thumbnail is
    the only image.
    """
    gallery = entry.get("gallery")
    if not gallery:
        return [(entry["file"], None)]
    out = []
    for g in gallery:
        if isinstance(g, str):
            out.append((g, None))
        else:
            out.append((g["file"], g.get("caption")))
    return out


def entry_files(entry):
    """Every media file an entry needs published, thumbnail included."""
    files = [entry["file"]]
    for f, _ in entry_images(entry):
        if f not in files:
            files.append(f)
    return files


def cname(league, cid):
    return next(c["name"] for c in league["coaches"] if c["id"] == cid)


# Populated in main() with the ids that actually get a profile page, so we
# never emit a link to a page that wasn't generated.
PROFILED = set()


def clink(league, cid, text=None):
    """Coach name, linked to their profile when one exists."""
    if not cid:
        return text or "CPU"
    label = text or cname(league, cid)
    if cid not in PROFILED:
        return label
    return ("<a href='coach-%s.html' class='clink'>%s</a>" % (cid, label))


def league_records(season_data, league, season_no):
    """Per-coach W-L for a season, counting every game the league played.

    Conference finals and playoff rounds are games too -- reading only "results"
    left conference champions a win short and their opponents a loss short.
    Regular-season games resolve at the week they were played so a team's CPU-era
    games don't land on the coach who has since left it; postseason games resolve
    at the end of the season.
    """
    rec = defaultdict(lambda: [0, 0])

    def add(winner, loser, week):
        for team, idx in ((winner, 0), (loser, 1)):
            cid = coach_for(league, team, season_no, week)
            if cid:
                rec[cid][idx] += 1

    # FW/SIM games (see profiles.exempt_tag) show on the site but stay out
    # of the user-vs-user records entirely.
    for r in season_data.get("results", []):
        if not profiles.exempt_tag(r):
            add(r["winner"], r["loser"], r["week"])
    for cc in season_data.get("conference_championships") or []:
        if not profiles.exempt_tag(cc):
            add(cc["winner"], cc["loser"], "PO")
    for bg in season_data.get("bowls") or []:
        if not profiles.exempt_tag(bg):
            add(bg["winner"], bg["loser"], "PO")
    for g in season_data.get("playoffs") or []:
        if not profiles.exempt_tag(g):
            add(g["winner"], g["loser"], "PO")

    out = [{"coach": cid, "w": w, "l": l} for cid, (w, l) in rec.items()]
    out.sort(key=lambda r: (-(r["w"] - r["l"]), -r["w"], r["coach"]))
    return out


def _chrono_games(league, all_seasons):
    """Every game ever played, in the order the league played them.

    Each entry resolves both coaches (None for CPU), keeps the score, and
    carries a human label ("Week 4", "SEC title", "Semifinal") so the record
    book can cite games without re-deriving anything.
    """
    labels = {"R1": "Playoff first round", "QF": "Quarterfinal",
              "SF": "Semifinal", "NC": "National Championship"}
    out = []
    for sd in all_seasons:
        sn = sd.get("season", 0)
        seq = []
        for r in sd.get("results", []):
            wk = r.get("week")
            seq.append((0, wk if isinstance(wk, int) else 0, r, "reg",
                        "Week %s" % wk, wk))
        for cc in sd.get("conference_championships") or []:
            seq.append((1, 0, cc, "conf", "%s title" % cc["conference"], "PO"))
        for bg in sd.get("bowls") or []:
            seq.append((2, 0, bg, "bowl", bg.get("bowl", "Bowl"), "PO"))
        for g in sd.get("playoffs") or []:
            seq.append((3, PO_ORDER.get(g.get("round"), 0), g, "playoff",
                        labels.get(g.get("round"), "Playoff"), "PO"))
        seq.sort(key=lambda e: (e[0], e[1]))
        for _, _, g, kind, label, wk in seq:
            out.append({
                "season": sn, "label": label, "kind": kind,
                "winner": g["winner"], "loser": g["loser"],
                "wc": coach_for(league, g["winner"], sn, wk),
                "lc": coach_for(league, g["loser"], sn, wk),
                "score": g.get("score"), "gotw": bool(g.get("gotw")),
                "exempt": profiles.exempt_tag(g),
                "site": g.get("site"), "round": g.get("round"),
            })
    return out


def compute_records(league, all_seasons, prof):
    """The league record book, derived entirely from the season files.

    Everything here respects the FW/SIM exemption -- a forfeit can't hold a
    league record -- and the head-to-head lists only count games where both
    sidelines had a user on them.
    """
    games = _chrono_games(league, all_seasons)
    played = [g for g in games if g["score"] and not g["exempt"]]
    h2h = [g for g in played if g["wc"] and g["lc"]]

    def marg(g):
        return g["score"][0] - g["score"][1]

    def tot(g):
        return g["score"][0] + g["score"][1]

    blowouts = sorted(h2h, key=lambda g: (-marg(g), -tot(g)))[:5]
    shootouts = sorted(h2h, key=lambda g: (-tot(g), marg(g)))[:5]
    thrillers = sorted(h2h, key=lambda g: (marg(g), -tot(g)))[:5]

    # Longest win streaks, counting every non-exempt game a coach played.
    runs = defaultdict(lambda: {"cur": 0, "curstart": None,
                                "best": 0, "span": None, "live": False})
    for g in played:
        for cid, won in ((g["wc"], True), (g["lc"], False)):
            if not cid:
                continue
            r = runs[cid]
            here = "S%d %s" % (g["season"], g["label"])
            if won:
                if r["cur"] == 0:
                    r["curstart"] = here
                r["cur"] += 1
                if r["cur"] >= r["best"]:
                    r["best"] = r["cur"]
                    r["span"] = (r["curstart"], here)
            else:
                r["cur"] = 0
    for r in runs.values():
        r["live"] = r["cur"] == r["best"] and r["best"] > 0
    streaks = sorted(
        ({"coach": cid, "n": r["best"], "span": r["span"], "live": r["live"]}
         for cid, r in runs.items() if r["best"] >= 3),
        key=lambda x: (-x["n"], x["coach"]))[:6]

    # Rivalries: every pairing, most-played first.
    wins = defaultdict(lambda: defaultdict(int))
    meetings = defaultdict(int)
    for g in h2h:
        key = frozenset((g["wc"], g["lc"]))
        if len(key) < 2:
            continue
        meetings[key] += 1
        wins[key][g["wc"]] += 1
    rivalries = []
    for key, n in sorted(meetings.items(), key=lambda kv: (-kv[1], sorted(kv[0]))):
        a, b = sorted(key, key=lambda cid: (-wins[key][cid], cid))
        rivalries.append({"a": a, "b": b, "aw": wins[key][a],
                          "bw": wins[key][b], "n": n})

    # GOTW ledger from the profile dossiers.
    gotw = sorted(
        ({"coach": cid, "w": p["gotw_w"], "l": p["gotw_l"]}
         for cid, p in prof.items() if p["gotw_w"] or p["gotw_l"]),
        key=lambda x: (-x["w"], x["l"], x["coach"]))

    titles = [g for g in games if g.get("round") == "NC" and g["score"]]

    return {"blowouts": blowouts, "shootouts": shootouts,
            "thrillers": thrillers, "streaks": streaks,
            "rivalries": rivalries, "gotw": gotw, "titles": titles}


def _rec_game(league, g, stat):
    """One record-book row for a single game, with the cited stat up front."""
    return (f"<div class='rec'><div class='k'>{stat}</div>"
            f"<div class='v'>{g['winner']} {g['score'][0]}&ndash;{g['score'][1]}"
            f" {g['loser']}</div>"
            f"<div class='d'>{clink(league, g['wc'])} over {clink(league, g['lc'])}"
            f" &middot; Season {g['season']} &middot; {g['label']}</div></div>")


def build_records(league, recs, bug=""):
    """The Record Book: superlatives, streaks, rivalries, and the title ledger."""
    b = ["""<div class="pagehead"><h1 class="page">The <em>Record Book</em></h1>
<p class="psub">Every number on this page is pulled straight from the results
&mdash; nothing is hand-kept. Forfeits and simmed games are exempt: a record has
to be earned on the sticks. Head-to-head marks only count games with a user on
both sidelines.</p></div>"""]
    rv = " data-rv" if MOTION else ""

    def game_section(title, note, rows, stat):
        if not rows:
            return
        b.append(f'<div class="section"{rv}><h2 class="sec">{title}</h2>'
                 f'<p class="secintro" style="font-size:14px;margin-top:-8px">{note}</p>'
                 f'<div class="recgrid">')
        b.extend(_rec_game(league, g, "%s #%d" % (stat, i + 1))
                 for i, g in enumerate(rows))
        b.append("</div></div>")

    game_section("Beatdowns", "The widest margins ever laid on another coach.",
                 recs["blowouts"], "Margin")
    game_section("Shootouts", "The most combined points two coaches ever hung up.",
                 recs["shootouts"], "Points")
    game_section("Photo finishes", "The closest calls in league history.",
                 recs["thrillers"], "Final margin")

    if recs["streaks"]:
        b.append(f'<div class="section"{rv}><h2 class="sec">Longest win streaks</h2>'
                 f'<div class="recgrid">')
        for s in recs["streaks"]:
            span = "%s &rarr; %s" % s["span"] if s["span"] else ""
            live = " &middot; <b style='color:var(--gold)'>active</b>" if s["live"] else ""
            b.append(f"<div class='rec'><div class='k'>{s['n']} straight</div>"
                     f"<div class='v'>{clink(league, s['coach'])}</div>"
                     f"<div class='d'>{span}{live}</div></div>")
        b.append("</div></div>")

    if recs["titles"]:
        b.append(f'<div class="section"{rv}><h2 class="sec">Title game ledger</h2>'
                 '<table><tr><th>Season</th><th>Champion</th><th>Score</th>'
                 '<th>Runner-up</th><th class="tb">Site</th></tr>')
        for g in reversed(recs["titles"]):
            b.append(f"<tr><td class='s'>S{g['season']}</td>"
                     f"<td class='w'>{g['winner']} "
                     f"<span style='color:var(--muted2)'>({clink(league, g['wc'])})</span></td>"
                     f"<td class='s'>{g['score'][0]}&ndash;{g['score'][1]}</td>"
                     f"<td style='color:var(--muted)'>{g['loser']} "
                     f"<span style='color:var(--muted2)'>({clink(league, g['lc'])})</span></td>"
                     f"<td class='tb' style='color:var(--muted)'>{g.get('site') or '&mdash;'}</td></tr>")
        b.append("</table></div>")

    if recs["rivalries"]:
        b.append(f'<div class="section"{rv}><h2 class="sec">The rivalries</h2>'
                 '<p class="secintro" style="font-size:14px;margin-top:-8px">'
                 'Every head-to-head series with multiple meetings, most-played first.</p>'
                 '<table><tr><th>Series</th><th>Meetings</th><th>Record</th><th>Edge</th></tr>')
        for rvl in recs["rivalries"]:
            if rvl["n"] < 2:
                continue
            edge = ("even" if rvl["aw"] == rvl["bw"]
                    else clink(league, rvl["a"]))
            b.append(f"<tr><td class='w'>{clink(league, rvl['a'])} "
                     f"<span style='color:var(--muted2)'>vs</span> "
                     f"{clink(league, rvl['b'])}</td>"
                     f"<td style='color:var(--muted)'>{rvl['n']}</td>"
                     f"<td class='s'>{rvl['aw']}&ndash;{rvl['bw']}</td>"
                     f"<td>{edge}</td></tr>")
        b.append("</table></div>")

    if recs["gotw"]:
        b.append(f'<div class="section"{rv}><h2 class="sec">Game of the Week ledger</h2>'
                 '<p class="secintro" style="font-size:14px;margin-top:-8px">'
                 'Records under the spotlight &mdash; GOTW games only.</p>'
                 '<table><tr><th>Coach</th><th>W&ndash;L</th></tr>')
        for row in recs["gotw"]:
            b.append(f"<tr><td class='w'>{clink(league, row['coach'])}</td>"
                     f"<td class='s'>{row['w']}&ndash;{row['l']}</td></tr>")
        b.append("</table></div>")

    return shell("The Record Book", "records.html", "\n".join(b), None, bug,
                 desc="Campus Kings league records — the biggest blowouts, "
                      "shootouts, streaks, rivalries, and every title game.")


def career_line(r):
    """Short résumé under a coach's name on the points leaderboard."""
    bits = []
    if r.get("titles"):
        bits.append("%d title%s" % (r["titles"], "" if r["titles"] == 1 else "s"))
    if r.get("runner_up"):
        bits.append("%d runner-up" % r["runner_up"])
    n = r.get("seasons", 0)
    bits.append("%d playoff appearance%s" % (n, "" if n == 1 else "s"))
    if len(r.get("teams", [])) > 1:
        bits.append("with " + ", ".join(r["teams"]))
    return ", ".join(bits)


def glance_figure(g, league, season):
    """Resolve an at_a_glance figure, deriving the ones that move.

    Write "auto:coaches" or "auto:season" as the figure in about.json and it is
    computed at build time. The roster changes with every auction, so a
    hand-typed count is wrong within a week.
    """
    fig = str(g.get("figure", ""))
    if fig == "auto:coaches":
        return sum(1 for c in league["coaches"]
                   if profiles.current_team(league, c["id"], season))
    if fig == "auto:season":
        return season
    if fig == "auto:seasons":
        return league["league"]["accredited_seasons"]
    return fig


def _latest_result(season_data):
    """(label, winner, score, loser) for the biggest most-recent game, or None."""
    entries = []
    for r in season_data.get("results", []):
        entries.append(((0, r["week"]), "Week %s" % r["week"], r))
    for cc in season_data.get("conference_championships") or []:
        entries.append(((1, 0), "%s title" % cc["conference"], cc))
    for g in season_data.get("playoffs") or []:
        rnd = g.get("round")
        lab = {"R1": "Playoff round 1", "QF": "Quarterfinal",
               "SF": "Semifinal", "NC": "National Championship"}.get(rnd, "Playoff")
        entries.append(((2, PO_ORDER.get(rnd, 0)), lab, g))
    if not entries:
        return None
    entries.sort(key=lambda e: e[0], reverse=True)
    lab, g = entries[0][1], entries[0][2]
    sc = "%d&ndash;%d" % tuple(g["score"]) if g.get("score") else "TBD"
    return lab, g["winner"], sc, g["loser"]


def glance_cell(g, league, season):
    """A glance figure, wrapped for the counter roll when it is a plain number."""
    v = glance_figure(g, league, season)
    if MOTION and str(v).isdigit():
        return "<span data-count='%s'>%s</span>" % (v, v)
    return v


def build_index(league, all_seasons, content, pts, about, bug="",
                belt=None, belt_titles=0, n_seasons=1, clips=None, recs=None):
    s2 = all_seasons[-1]
    season = s2.get("season", league["league"]["current_season"])
    # Gameplay behind the hero. The poster frame paints first so there is never
    # a blank band, and it is all that shows for reduced-motion visitors -- the
    # CSS hides the video element rather than letting it autoplay.
    if clips and HERO_VIDEO:
        srcs = "".join('<source src="%s" type="video/%s">'
                       % (u, "webm" if u.endswith(".webm") else "mp4")
                       for u in clips[0])
        banner_html = (
            '<div class="banner"></div>'
            '<video class="herovid" autoplay muted loop playsinline preload="auto" '
            'poster="media/video/hero-poster.jpg" '
            'data-clips=\'%s\'>%s</video>' % (json.dumps(clips), srcs))
    else:
        banner_html = '<div class="banner"></div>'

    heroflash_html = ""
    if MOTION:
        latest = _latest_result(s2)
        if latest:
            lab, w, sc, l = latest
            heroflash_html = (
                "<div class='heroflash' data-key='s%d-%s-%s'><span class='in'>"
                "<span class='fw'>%s <span class='fs'>%s</span> %s</span>"
                "<span class='fl'>%s &middot; final</span></span></div>"
                % (season, lab.lower().replace(" ", ""), w.lower().replace(" ", "-"),
                   w, sc, l, lab))

    # Reigning champion: the newest season whose title game has been played.
    done = [d for d in all_seasons if bracket_is_final(d)]
    champ_info = None
    if done:
        sd = done[-1]
        nc = next(g for g in sd["playoffs"] if g["round"] == "NC")
        cteam = sd.get("champion") or nc["winner"]
        champ_info = {
            "season": sd.get("season", 0), "team": cteam,
            "coach": coach_for(league, cteam, sd.get("season", 0)),
            "runner": sd.get("runner_up") or nc["loser"],
            "score": nc.get("score"), "site": nc.get("site"),
        }

    stinger_html = ""
    if champ_info:
        stinger_html = (
            "<div class='stinger'><b>Season %s champion</b>"
            "<span class='sep'>&mdash;</span>%s &middot; %s</div>"
            % (season_word(champ_info["season"]), champ_info["team"],
               cname(league, champ_info["coach"]) if champ_info["coach"] else "CPU"))

    hero = (f'<div class="hero">'
            f'{banner_html}<div class="scrim"></div>'
            f'{heroflash_html}'
            f'<div class="inner">'
            f'<div class="eyebrow">Campus Kings &middot; Season '
            f'{league["league"]["current_season"]}</div>'
            f'<h1>{about.get("hero_html") or "Twenty seasons.<br>One dynasty.<br><em>One belt.</em>"}</h1>'
            f'{stinger_html}'
            f'<div class="scrollcue">Scroll'
            f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#dfa839" '
            f'stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></div>'
            f'</div></div>'
            f'<div class="quick">'
            f'<a href="standings.html"><div class="qk">{NAV[1][1]} <span>&rarr;</span></div>'
            f'<div class="qd">The championship race, weekly results</div></a>'
            f'<a href="coaches.html"><div class="qk">Coaches <span>&rarr;</span></div>'
            f'<div class="qd">Profiles, rings, full game logs</div></a>'
            f'<a href="records.html"><div class="qk">Records <span>&rarr;</span></div>'
            f'<div class="qd">Blowouts, streaks, rivalries</div></a>'
            f'<a href="history.html"><div class="qk">History <span>&rarr;</span></div>'
            f'<div class="qd">Champions, brackets, moves</div></a>'
            f'</div>'
            f'<div class="glance"><div class="inner">'
            + "".join(f"<div class='cell'><div class='fig'>{glance_cell(g, league, season)}</div>"
                      f"<div class='lab'>{g['label']}</div></div>"
                      for g in about["at_a_glance"])
            + "</div></div>")

    rv = " data-rv" if MOTION else ""

    # ---- The Throne: reigning champion beside the belt race ----
    if belt:
        belt_names = " &middot; ".join(clink(league, r["coach"]) for r in belt)
    else:
        belt_names = "Up for grabs"
    live_now = bool(s2.get("playoffs") or s2.get("playoff_seeds")) \
        and not bracket_is_final(s2)

    total = league["league"]["accredited_seasons"]
    live_ct = 1 if live_now else 0
    if MOTION:
        segs = "".join(
            "<i class='on'></i>" if i < n_seasons else
            ("<i class='live'></i>" if i < n_seasons + live_ct else "<i></i>")
            for i in range(total))
        beltbar_html = (
            "<div class='beltbar' data-done='%d' data-live='%d'>%s</div>"
            "<div class='beltbar-lab'>%d of %d seasons decided</div>"
            % (n_seasons, live_ct, segs, n_seasons, total))
        # one-time confetti when the newest season's title game is fresh
        if bracket_is_final(s2):
            champ = s2.get("champion") or next(g["winner"] for g in s2["playoffs"]
                                               if g["round"] == "NC")
            beltbar_html += ("<span data-champion='s%d-%s' style='display:none'></span>"
                             % (season, champ.lower().replace(" ", "-")))
    else:
        beltbar_html = ""

    # The title race, coach by coach -- everyone with at least one ring.
    holders = [r for r in pts if r.get("titles")]
    race_html = "".join(
        "<div class='rc'><div class='n'%s>%d</div><div class='w'>%s</div></div>"
        % ((" data-count='%d'" % r["titles"]) if MOTION else "",
           r["titles"], clink(league, r["coach"]))
        for r in holders)

    if champ_info and champ_info["score"]:
        ch_sub = ("Beat %s %d&ndash;%d%s" %
                  (champ_info["runner"], champ_info["score"][0],
                   champ_info["score"][1],
                   (" in %s" % champ_info["site"]) if champ_info["site"] else ""))
        champ_panel = (
            f"<div class='belt'><div class='lbl'>Reigning national champion "
            f"&middot; Season {season_word(champ_info['season'])}</div>"
            f"<div class='who'>{champ_info['team']}</div>"
            f"<div class='meta' style='font-size:14px'><b>"
            f"{clink(league, champ_info['coach'])}</b> &middot; {ch_sub}</div></div>")
    else:
        champ_panel = ("<div class='belt'><div class='lbl'>National champion</div>"
                       "<div class='who'>To be decided</div>"
                       "<div class='meta'>The first title game hasn't been played "
                       "yet.</div></div>")

    if not race_html:
        race_html = ("<div class='rc'><div class='n'>0</div>"
                     "<div class='w'>No rings yet</div></div>")
    lead_word = "leads" if belt and len(belt) == 1 else "lead"
    belt_panel = (
        f"<div class='belt'><div class='lbl'>The Campus King Belt</div>"
        f"<div class='race'>{race_html}</div>"
        f"<div class='meta'>Most national titles across {total} accredited "
        f"seasons takes the belt. {belt_names} {lead_word} it today.</div>"
        f"{beltbar_html}</div>")

    dynasty_html = ""
    if done:
        chips = []
        for sd in done:
            nc = next(g for g in sd["playoffs"] if g["round"] == "NC")
            t = sd.get("champion") or nc["winner"]
            cid = coach_for(league, t, sd.get("season", 0))
            chips.append("<a class='dyn' href='history.html'>"
                         "<span class='s'>S%d</span><b>%s</b>"
                         "<span class='c'>%s</span></a>"
                         % (sd.get("season", 0), t,
                            cname(league, cid) if cid else "CPU"))
        dynasty_html = "<div class='dynasty'>%s</div>" % "".join(chips)

    b = [f'<div class="section"{rv}><h2 class="sec">The Throne</h2>'
         f'<div class="throne">{champ_panel}{belt_panel}</div>{dynasty_html}</div>']

    # ---- Playoff Points ladder ----
    pts_label = ("season one" if n_seasons == 1
                 else "through %d seasons" % n_seasons)
    if live_now:
        pts_label += " &middot; season %d in progress" % season
    b.append(f'<div class="section"{rv}>'
             f'<h2 class="sec">Playoff Points &middot; {pts_label}</h2>')
    top_pts = max((r["points"] for r in pts[:8]), default=0) or 1
    for r in pts[:8]:
        bar = ("<i class='ptbar' style='--w:%d%%'></i>"
               % round(100 * r["points"] / top_pts))
        lead = " lead" if r.get("rank") == 1 else ""
        b.append(f"""<div class="row{lead}">{bar}<span class="num">{r['rank']}</span><div class="bd">
<span class="tm">{clink(league, r['coach'])}</span><span class="co">{r['team']}</span>
<div class="dt">{career_line(r)}</div></div>
<span class="rt">{r['points']}<small>pts</small></span></div>""")
    b.append('<div class="dt" style="padding-top:16px">'
             '<a href="standings.html" style="color:var(--gold)">Full standings &rarr;</a></div></div>')

    # ---- Record book teaser ----
    if recs:
        tiles = []
        for key, label in (("blowouts", "Biggest beatdown"),
                           ("shootouts", "Biggest shootout"),
                           ("thrillers", "Closest finish")):
            if recs[key]:
                tiles.append(_rec_game(league, recs[key][0], label))
        if recs["streaks"]:
            s = recs["streaks"][0]
            span = "%s &rarr; %s" % s["span"] if s["span"] else ""
            live = " &middot; <b style='color:var(--gold)'>active</b>" if s["live"] else ""
            tiles.append(f"<div class='rec'><div class='k'>Longest win streak</div>"
                         f"<div class='v'>{s['n']} straight &middot; "
                         f"{clink(league, s['coach'])}</div>"
                         f"<div class='d'>{span}{live}</div></div>")
        if tiles:
            b.append(f'<div class="section"{rv}><h2 class="sec">From the record book</h2>'
                     f'<div class="recgrid">{"".join(tiles)}</div>'
                     '<div class="dt" style="padding-top:16px">'
                     '<a href="records.html" style="color:var(--gold)">'
                     'The full record book &rarr;</a></div></div>')

    # ---- Latest content ----
    b.append(f'<div class="section"{rv}><h2 class="sec">Latest content</h2><div class="grid">')
    for c in content["content"][:6]:
        b.append(content_card(c))
    b.append("</div>")
    if len(content["content"]) > 6:
        b.append('<div class="dt" style="padding-top:18px">'
                 '<a href="content.html" style="color:var(--gold)">'
                 'Full archive &rarr;</a></div>')
    b.append("</div>")

    # ---- Who we are / how a week works / getting in ----
    b.append(f'<div class="section"{rv}><h2 class="sec">Who we are</h2>'
             f'<p class="secintro">{about["intro"]}</p><div class="pillars">'
             + "".join(f"<div class='pillar'><div class='n'>{p['num']}</div>"
                       f"<h3>{p['title']}</h3><p>{p['body']}</p></div>"
                       for p in about["pillars"]) + "</div></div>")

    b.append(f'<div class="section"{rv}><h2 class="sec">How a week works</h2><div class="steps">'
             + "".join(f"<div class='step'><div class='k'>{s['step']}</div>"
                       f"<p>{s['text']}</p></div>" for s in about["how_it_works"])
             + "</div></div>")

    b.append(f"""<div class="section"{rv}><h2 class="sec">{about['join']['title']}</h2>
<p style="font-size:14.5px;color:var(--muted);line-height:1.7;max-width:680px;margin:0">
{about['join']['body']}</p></div>""")

    return shell("Home", "index.html", "\n".join(b), hero, bug,
                 desc=about.get("tagline"))


def content_card(c):
    """One card in a content grid. Links to the write-up when there is one."""
    tag = '<span class="tag">Write-up</span>' if c.get("article") else ""
    kind = html.escape(c["kind"], quote=True)
    return (f'<a class="card" data-kind="{kind}" href="{article_path(c)}">'
            f'<img src="media/{c["file"]}" alt="{html.escape(c["title"], quote=True)}" loading="lazy" decoding="async">'
            f'<div class="body"><div class="kind">{c["kind"]} &middot; S{c["season"]}</div>'
            f'<div class="ttl">{c["title"]}{tag}</div><div class="bl">{c["blurb"]}</div>'
            f'<div class="dte">{fmt_date(c["date"])}</div></div></a>')


def build_content(content, bug=""):
    """Full archive of every published graphic and write-up, newest season first."""
    items = content["content"]
    by_season = defaultdict(list)
    for c in items:
        by_season[c["season"]].append(c)

    blurb = ("Every recap, ranking, and graphic ever published &mdash; %d and "
             "counting, %d with a full write-up. Nothing falls off this page."
             % (len(items), sum(1 for c in items if c.get("article"))))
    b = [f"""<div class="pagehead"><h1 class="page">The <em>Archive</em></h1>
<p class="psub">{blurb}</p></div>"""]

    if DYNAMIC:
        kinds = sorted({c["kind"] for c in items})
        chips = ['<button class="chip on" type="button" data-kind="all">All</button>']
        chips += ['<button class="chip" type="button" data-kind="%s">%s</button>'
                  % (html.escape(k, quote=True), html.escape(k)) for k in kinds]
        b.append('<div class="section" style="padding-bottom:0;border-bottom:none">'
                 '<input class="searchbar" type="search" placeholder="Search the archive&hellip;" '
                 'data-filter=".card[data-kind]" aria-label="Search the archive">'
                 '<div class="chips">' + "".join(chips) + "</div></div>")

    for season in sorted(by_season, reverse=True):
        b.append(f'<div class="section"><h2 class="sec">Season {season}</h2><div class="grid">')
        for c in sorted(by_season[season], key=lambda c: c["date"], reverse=True):
            b.append(content_card(c))
        b.append("</div></div>")
    return shell("Archive", "content.html", "\n".join(b), None, bug,
                 desc="Every recap, power ranking, and graphic Campus Kings "
                      "has published, season by season.")


def build_article(c, body_md, bug=""):
    """A single write-up: graphic(s) on top, prose below."""
    hero = (f'<div class="hero" style="padding:0;background:var(--bg)">'
            f'<div class="inner" style="padding:56px 24px 40px;text-align:left;max-width:1000px">'
            f'<div class="eyebrow">{c["kind"]} &middot; Season {c["season"]}</div>'
            f'<h1 style="font-size:clamp(30px,5vw,52px)">{c["title"]}</h1>'
            f'<p class="lede" style="margin:0;max-width:620px">{c["blurb"]}</p>'
            f'</div></div>')

    posters = []
    for f, cap in entry_images(c):
        label = cap or "Open the full graphic &rarr;"
        posters.append(
            f'<a class="poster" href="media/{f}">'
            f'<img src="media/{f}" alt="{html.escape(cap or c["title"], quote=True)}" loading="lazy" decoding="async">'
            f'<div class="cap">{label}</div></a>')

    b = [f'<div class="section" style="border-bottom:none">',
         f'<div class="byline">Published {fmt_date(c["date"])}</div>',
         "\n".join(posters),
         f'<div class="article">{markdown(body_md)}</div>',
         f'<div class="backlink"><a href="content.html">&larr; All content</a></div>',
         f'</div>']
    return shell(c["title"], "content.html", "\n".join(b), hero, bug,
                 desc=c.get("blurb"), path=article_path(c))


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
    return shell("Rules", "rules.html", inner, None, bug,
                 desc="The Campus Kings rulebook — league settings, bans, "
                      "scheduling, and how Playoff Points are earned.")


def build_standings(league, s2, pts, bug="", n_seasons=1,
                    belt=None, belt_titles=0):
    # This season's W-L, folded into the race table as a column so replacing the
    # old head-to-head standings doesn't lose it.
    sn = s2.get("season", league["league"]["current_season"])
    season_wl = {r["coach"]: (r["w"], r["l"])
                 for r in league_records(s2, league, sn)}

    # compute_all() only makes rows for coaches who have scored, so on its own the
    # table would show 11 of 31. Everyone currently holding a team belongs in the
    # race at zero; coaches who have earned points keep their row even if they've
    # since left.
    field = list(pts)
    scored = {r["coach"] for r in field}
    for c in league["coaches"]:
        cid = c["id"]
        if cid in scored:
            continue
        team = profiles.current_team(league, cid, sn)
        if not team:
            continue
        field.append({"coach": cid, "team": team, "points": 0, "titles": 0,
                      "runner_up": 0, "seasons": 0, "nc_apps": 0,
                      "final_fours": 0, "rank": len(pts) + 1})
    race = sorted(field, key=lambda r: (r.get("rank") or 99, r["coach"]))
    # a season only counts as decided once its title game is in
    decided = n_seasons - (1 if (s2.get("playoffs") or s2.get("playoff_seeds"))
                           and not bracket_is_final(s2) else 0)

    b = [f"""<div class="pagehead"><h1 class="page">The <em>Belt</em></h1>
<p class="psub">The belt goes to whoever wins the most national championships across the
20 accredited seasons. Playoff Points are a separate, cumulative ladder &mdash; they only
move in the postseason, so the standings hold still until a bracket finishes.</p></div>"""]

    if belt:
        holder = " &middot; ".join(clink(league, r["coach"]) for r in belt)
        line = "%d national championship%s%s" % (
            belt_titles, "" if belt_titles == 1 else "s",
            " each" if len(belt) > 1 else "")
    else:
        holder, line = "Up for grabs", "No titles awarded yet"
    b.append(f'<div class="section"><div class="belt"><div class="lbl">Holding the belt</div>'
             f'<div class="who">{holder}</div>'
             f'<div class="meta">{line} &middot; '
             f'{decided} of {league["league"]["accredited_seasons"]} accredited '
             f'seasons decided.</div></div></div>')

    b.append('<div class="section"><h2 class="sec">Playoff Points standings</h2>'
             '<p class="dt" style="margin:-8px 0 16px">Cumulative: +1 making the field, '
             '+2 round two, +3 Final Four, +4 the title game, +8 winning it, plus the '
             'conference bonus (SEC / B1G / Big 12 +2, ACC +1). Ties break on '
             'championships, then title-game appearances, then Final Fours, then total '
             'playoff appearances. "This season" is league games only.</p>'
             f'<table{" class=sortable" if DYNAMIC else ""}>'
             '<tr><th>#</th><th>Coach</th><th>Team</th><th>Pts</th>'
             '<th>Titles</th><th class="tb">Title&nbsp;games</th>'
             '<th class="tb">Final&nbsp;Fours</th><th class="tb">Playoffs</th>'
             '<th>This season</th></tr>')
    for r in race:
        w, l = season_wl.get(r["coach"], (0, 0))
        dash = "<span style='color:var(--muted2)'>&mdash;</span>"
        wl = ("%d&ndash;%d" % (w, l)) if (w or l) else dash
        b.append(f"<tr><td>{r.get('rank') or dash}</td>"
                 f"<td class='w'>{clink(league, r['coach'])}</td>"
                 f"<td style='color:var(--muted)'>{r['team']}</td>"
                 f"<td class='s'>{r['points']}</td>"
                 f"<td class='s'>{r['titles'] or dash}</td>"
                 f"<td class='tb' style='color:var(--muted)'>{r.get('nc_apps', 0) or dash}</td>"
                 f"<td class='tb' style='color:var(--muted)'>{r.get('final_fours', 0) or dash}</td>"
                 f"<td class='tb' style='color:var(--muted)'>{r.get('seasons', 0) or dash}</td>"
                 f"<td style='color:var(--muted)'>{wl}</td></tr>")
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
            ex = profiles.exempt_tag(r)
            if ex:
                tag += '<span class="tag">%s</span>' % ex
            b.append(f"<tr><td class='w'>{r['winner']}{tag}</td>"
                     f"<td style='color:var(--muted)'>over {r['loser']}</td>"
                     f"<td class='s'>{sc}</td></tr>")
        b.append("</table>")
    b.append("</div>")

    # The in-game poll table used to sit here. It was hand-maintained and always
    # drifting, so it's gone; "poll_snapshot" in the season file is now unused.

    ccs = s2.get("conference_championships") or []
    if ccs:
        b.append('<div class="section"><h2 class="sec">Conference championships</h2><table>')
        for cc in ccs:
            wc = coach_for(league, cc["winner"], sn)
            lc = coach_for(league, cc["loser"], sn)
            sc = ("%d&ndash;%d" % tuple(cc["score"])) if cc.get("score") else "TBD"
            ex = profiles.exempt_tag(cc)
            if ex:
                sc += ' <span class="tag">%s</span>' % ex
            b.append("<tr><td class='s' style='width:66px'>%s</td>"
                     "<td class='w'>%s</td>"
                     "<td style='color:var(--muted)'>over %s</td>"
                     "<td class='s'>%s</td></tr>"
                     % (cc["conference"],
                        "%s <span style='color:var(--muted2)'>(%s)</span>"
                        % (cc["winner"], clink(league, wc) if wc else "CPU"),
                        "%s <span style='color:var(--muted2)'>(%s)</span>"
                        % (cc["loser"], clink(league, lc) if lc else "CPU"), sc))
        b.append("</table></div>")

    bowl_games = s2.get("bowls") or []
    if bowl_games:
        b.append('<div class="section"><h2 class="sec">Bowl games</h2>'
                 '<p class="dt" style="margin:-8px 0 16px">Outside the bracket, so they '
                 'count in records but earn no Playoff Points.</p><table>')
        for bg in bowl_games:
            wc = coach_for(league, bg["winner"], sn)
            lc = coach_for(league, bg["loser"], sn)
            sc = ("%d&ndash;%d" % tuple(bg["score"])) if bg.get("score") else "TBD"
            ex = profiles.exempt_tag(bg)
            if ex:
                sc += ' <span class="tag">%s</span>' % ex
            b.append("<tr><td class='s' style='width:96px'>%s</td>"
                     "<td class='w'>%s <span style='color:var(--muted2)'>(%s)</span></td>"
                     "<td style='color:var(--muted)'>over %s "
                     "<span style='color:var(--muted2)'>(%s)</span></td>"
                     "<td class='s'>%s</td></tr>"
                     % (bg.get("bowl", "Bowl"), bg["winner"],
                        clink(league, wc) if wc else "CPU", bg["loser"],
                        clink(league, lc) if lc else "CPU", sc))
        b.append("</table></div>")

    # Playoff games for a season still in progress. Once the NC row lands the
    # season is scored normally and the finished bracket moves to History, so
    # this section disappears on its own.
    live = live_bracket(s2)
    if live:
        labels = {"R1": "First round", "QF": "Quarterfinals",
                  "SF": "Semifinals", "NC": "National Championship"}
        b.append('<div class="section"><h2 class="sec">Playoff bracket &middot; in progress</h2>'
                 '<p class="dt" style="margin:-8px 0 16px">Rounds appear as results are '
                 'entered. Playoff Points and the Belt update once the title game is in.</p>')
        for rnd in ("R1", "QF", "SF", "NC"):
            rows = [g for g in live if g.get("round") == rnd]
            if not rows:
                continue
            b.append(f'<div class="wklabel">{labels[rnd]}</div><table>')
            for g in rows:
                tags = "".join('<span class="tag">%s</span>' % g[k]
                               for k in ("bowl", "note") if g.get(k))
                sc = ("%d&ndash;%d" % tuple(g["score"])) if g.get("score") else "TBD"
                wc = coach_for(league, g["winner"], sn)
                lc = coach_for(league, g["loser"], sn)
                b.append("<tr><td class='w'>%s%s</td>"
                         "<td style='color:var(--muted)'>over %s</td>"
                         "<td class='s'>%s</td></tr>"
                         % ("%s <span style='color:var(--muted2)'>(%s)</span>"
                            % (g["winner"], clink(league, wc) if wc else "CPU"), tags,
                            "%s <span style='color:var(--muted2)'>(%s)</span>"
                            % (g["loser"], clink(league, lc) if lc else "CPU"), sc))
            b.append("</table>")
        b.append("</div>")

    return shell("The Belt", "standings.html", "\n".join(b), None, bug,
                 desc="Playoff Points standings, weekly results, and the race "
                      "for the Campus King Belt.")


ORDINALS = ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
            "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
            "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty")


def season_word(n):
    """3 -> 'Three'. Falls back to the digit past the accredited cycle."""
    return ORDINALS[n] if 0 <= n < len(ORDINALS) else str(n)


def build_history(league, all_seasons, bug=""):
    """Every completed season, newest first, then the coaching-move log."""
    b = ['<div class="pagehead"><h1 class="page">League <em>History</em></h1>'
         '<p class="psub">Champions, brackets, and how every coach got where they '
         'are.</p></div>']

    labels = {"R1": "First round", "QF": "Quarterfinals",
              "SF": "Semifinals", "NC": "National Championship"}

    # Newest first, and only seasons whose title game has been played.
    done = [d for d in all_seasons if bracket_is_final(d)]
    for sd in reversed(done):
        sn = sd.get("season", 0)
        word = season_word(sn)
        nc = next(g for g in sd["playoffs"] if g["round"] == "NC")
        champ = sd.get("champion") or nc["winner"]
        runner = sd.get("runner_up") or nc["loser"]
        seeds = sd.get("playoff_seeds") or {}
        seed_of = {t: k for k, t in seeds.items()}
        as_seed = (" &mdash; as a %s seed." % seed_of[champ]) if champ in seed_of else "."
        b.append(f'<div class="section"><div class="belt">'
                 f'<div class="lbl">Season {word} champion</div>'
                 f'<div class="who">{champ} &middot; '
                 f'{clink(league, coach_for(league, champ, sn))}</div>'
                 f'<div class="meta">Beat {runner} '
                 f'({clink(league, coach_for(league, runner, sn))}) '
                 f'{nc["score"][0]}&ndash;{nc["score"][1]} in '
                 f'{nc.get("site", "the final")}{as_seed}</div></div></div>')

        b.append(f'<div class="section"><h2 class="sec">Season {word} playoff '
                 f'bracket</h2>')
        for rnd in ("R1", "QF", "SF", "NC"):
            rows = [x for x in sd["playoffs"] if x["round"] == rnd]
            if not rows:
                continue
            b.append(f'<div class="wklabel">{labels[rnd]}</div><table>')
            for g in rows:
                extra = "".join('<span class="tag">%s</span>' % g[k]
                                for k in ("bowl", "note") if g.get(k))
                sc = ("%d&ndash;%d" % tuple(g["score"])) if g.get("score") else "TBD"
                b.append(f"<tr><td class='w'>{g['winner']}{extra}</td>"
                         f"<td style='color:var(--muted)'>over {g['loser']}</td>"
                         f"<td class='s'>{sc}</td></tr>")
            b.append("</table>")
        b.append("</div>")

        recs = sd.get("regular_season_records") or {}
        if recs:
            def _wl(v):
                w, l = v.split("-")
                return (-int(w), int(l))
            b.append(f'<div class="section"><h2 class="sec">Season {word} final '
                     f'standings</h2><table><tr><th>#</th><th>Team</th>'
                     f'<th>Coach</th><th>W&ndash;L</th></tr>')
            for i, (team, rec) in enumerate(
                    sorted(recs.items(), key=lambda kv: _wl(kv[1])), 1):
                cid = coach_for(league, team, sn)
                who = clink(league, cid) if cid else \
                    "<span style='color:var(--muted2)'>CPU</span>"
                b.append("<tr><td>%d</td><td class='w'>%s</td>"
                         "<td style='color:var(--muted)'>%s</td>"
                         "<td class='s'>%s</td></tr>"
                         % (i, team, who, rec.replace("-", "&ndash;")))
            b.append("</table></div>")

    if not done:
        b.append('<div class="section"><p class="dt">No season has been '
                 'completed yet.</p></div>')

    b.append('<div class="section"><h2 class="sec">Coaching moves</h2><table><tr>'
             '<th>Team</th><th>Coach</th><th>From</th><th>Note</th></tr>')
    for t in league["tenures"]:
        if not t.get("note"):
            continue
        b.append(f"<tr><td class='w'>{t['team']}</td>"
                 f"<td style='color:var(--muted)'>{clink(league, t['coach'])}</td>"
                 f"<td class='s' style='font-size:13px'>{t['from']}</td>"
                 f"<td style='color:var(--muted);font-size:12.5px'>{t['note']}</td></tr>")
    b.append("</table></div>")
    return shell("History", "history.html", "\n".join(b), None, bug,
                 desc="Every champion, playoff bracket, and coaching move in "
                      "Campus Kings history.")


def load_all_seasons(league):
    """Every season_NN.json that exists, in order.

    main() used to name season_01 and season_02 literally, which meant adding a
    season meant editing code. Now dropping season_03.json in data/ is enough.
    """
    out = []
    for n in range(1, league["league"]["accredited_seasons"] + 1):
        f = DATA / ("season_%02d.json" % n)
        if f.exists():
            out.append(json.loads(f.read_text(encoding="utf-8")))
    if not out:
        raise SystemExit("No season files found in %s" % DATA)
    return out


def main():
    league = load("league.json")
    content, about, rules = load("content.json"), load("about.json"), load("rules.json")
    all_seasons = load_all_seasons(league)
    cur_season = all_seasons[-1]          # newest file drives the live pages
    seasons = completed_seasons(league)
    pts = compute_all(league, seasons)
    belt, belt_titles = belt_leaders(pts)
    bug = ticker(cur_season)

    SITE.mkdir(exist_ok=True)
    (SITE / "media").mkdir(exist_ok=True)
    # Tell GitHub Pages to serve these files as-is instead of running Jekyll
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    LOGO_FILES = ("logo.png", "logo-mark.png", "favicon.png", "hero-banner.jpg")
    for f in LOGO_FILES:
        src = MEDIA_SRC / f
        if src.exists():
            shutil.copy(src, SITE / "media" / f)

    # Hero clips. Any mp4 in media_src/video/ is picked up automatically, so
    # adding a highlight is dropping a file in -- no code change.
    clips = []
    # Accept any casing of the folder name: Windows treats video/ and Video/
    # as the same directory, but the Actions runner is case-sensitive Linux,
    # and a mismatch there silently built a hero with no clips at all.
    vsrc = next((d for d in MEDIA_SRC.iterdir()
                 if d.is_dir() and d.name.lower() == "video"),
                MEDIA_SRC / "video")
    if vsrc.is_dir():
        (SITE / "media" / "video").mkdir(exist_ok=True)
        groups = {}
        for f in sorted(vsrc.iterdir()):
            if f.suffix.lower() not in (".webm", ".mp4", ".jpg"):
                continue
            shutil.copy(f, SITE / "media" / "video" / f.name)
            if f.suffix.lower() in (".webm", ".mp4"):
                # one entry per highlight, listing whichever formats exist, so
                # rotation advances between clips and not between encodings
                groups.setdefault(f.stem, []).append("media/video/" + f.name)
        for stem in sorted(groups):
            # webm first where present; mp4 is the universal fallback
            clips.append(sorted(groups[stem], key=lambda u: not u.endswith(".webm")))
        if clips:
            print("  %d hero clip(s)" % len(clips))

    copied = 0
    total = 0
    missing = []
    for c in content["content"]:
        for f in entry_files(c):
            total += 1
            dest = SITE / "media" / f
            src = MEDIA_SRC / f
            if src.exists():
                shutil.copy(src, dest)
                copied += 1
            elif dest.exists():
                copied += 1          # already published in a previous build
            else:
                missing.append(f)
    if missing:
        print("  WARNING missing image(s): %s" % ", ".join(missing))
        print("  Put them in %s/ or docs/media/" % MEDIA_SRC.name)

    # Resolve write-ups before writing any page, so a card can never link to a
    # post that wasn't generated (same reason PROFILED is computed up front).
    for c in content["content"]:
        if c.get("article") and not (ARTICLES / c["article"]).exists():
            print("  WARNING missing article: %s (referenced by %r) — "
                  "card will link to the image instead"
                  % (c["article"], c["title"]))
            c.pop("article")

    # Work out who gets a profile first, so coach names can link everywhere.
    prof = profiles.gather(league, all_seasons)
    cur = league["league"]["current_season"]
    legacy = league.get("legacy_championships", {})
    roster = [c["id"] for c in league["coaches"]
              if profiles.current_team(league, c["id"], cur)
              or legacy.get(c["id"]) or prof.get(c["id"])]
    PROFILED.update(roster)
    profiles.PROFILED = PROFILED
    profiles.clink = clink
    profiles.DYNAMIC = DYNAMIC

    recs = compute_records(league, all_seasons, prof)

    (SITE / "index.html").write_text(build_index(league, all_seasons, content, pts, about, bug, belt, belt_titles, len(seasons), clips, recs), encoding="utf-8")
    (SITE / "standings.html").write_text(build_standings(league, cur_season, pts, bug, len(seasons), belt, belt_titles), encoding="utf-8")
    (SITE / "records.html").write_text(build_records(league, recs, bug), encoding="utf-8")
    (SITE / "rules.html").write_text(build_rules(rules, bug), encoding="utf-8")
    (SITE / "history.html").write_text(build_history(league, all_seasons, bug), encoding="utf-8")
    (SITE / "coaches.html").write_text(
        profiles.index_page(league, prof, shell, bug, cur), encoding="utf-8")
    (SITE / "content.html").write_text(build_content(content, bug), encoding="utf-8")
    for cid in roster:
        (SITE / ("coach-%s.html" % cid)).write_text(
            profiles.coach_page(league, cid, prof, shell, bug, cur), encoding="utf-8")

    # Long-form write-ups: one page per manifest entry that names an article file
    posts = 0
    for c in content["content"]:
        if not c.get("article"):
            continue
        body = (ARTICLES / c["article"]).read_text(encoding="utf-8")
        (SITE / article_path(c)).write_text(
            build_article(c, body, bug), encoding="utf-8")
        posts += 1

    # Site search index: one JSON the navbar palette fetches on first open.
    # Everything searchable gets a row -- kind, title, subtitle, href.
    if DYNAMIC:
        ix = []
        for href, label, sub in (
                ("standings.html", "The Belt", "standings and weekly results"),
                ("coaches.html", "Coaches", "every coach, rings, game logs"),
                ("records.html", "The Record Book", "blowouts, streaks, rivalries"),
                ("content.html", "The Archive", "every graphic and write-up"),
                ("rules.html", "Rulebook", "settings, bans, scheduling"),
                ("history.html", "History", "champions, brackets, moves")):
            ix.append({"k": "Page", "t": label, "s": sub, "h": href})
        for cid in roster:
            cname = next(c["name"] for c in league["coaches"] if c["id"] == cid)
            team = profiles.current_team(league, cid, cur)
            ix.append({"k": "Coach", "t": cname,
                       "s": team or "former coach", "h": "coach-%s.html" % cid})
            if team:
                ix.append({"k": "Team", "t": team,
                           "s": "coached by %s" % cname, "h": "coach-%s.html" % cid})
        for c in content["content"]:
            ix.append({"k": c["kind"], "t": c["title"],
                       "s": "Season %d · %s" % (c["season"], fmt_date(c["date"])),
                       "h": article_path(c)})
        ROUNDS = {"R1": "first round", "QF": "quarterfinal",
                  "SF": "semifinal", "NC": "national championship"}
        for s in all_seasons:
            sn = s["season"]
            h = "history.html" if s.get("status") == "complete" else "standings.html"
            def game(g, sub):
                ex = profiles.exempt_tag(g)
                ix.append({"k": "Result",
                           "t": "%s %d–%d %s" % (g["winner"], g["score"][0],
                                                 g["score"][1], g["loser"]),
                           "s": sub + (" · %s" % ex if ex else ""), "h": h})
            for r in s.get("results", []):
                wk = r["week"] if isinstance(r["week"], str) else "Week %s" % r["week"]
                game(r, "Season %d · %s%s"
                     % (sn, wk, " · GOTW" if r.get("gotw") else ""))
            for g in s.get("conference_championships", []):
                game(g, "Season %d · %s championship" % (sn, g["conference"]))
            for g in s.get("playoffs", []):
                game(g, "Season %d · %s" % (sn, ROUNDS.get(g["round"], "playoff")))
            for g in s.get("bowls", []):
                game(g, "Season %d · bowl game" % sn)
        (SITE / "search-index.json").write_text(
            json.dumps(ix, ensure_ascii=False), encoding="utf-8")

    # 404 for GitHub Pages. Links are absolute -- a bad URL can be arbitrarily
    # deep, and relative links would 404 right back.
    not_found = (f'<div class="pagehead"><h1 class="page">Fourth <em>down</em></h1>'
                 f'<p class="psub">That page doesn\'t exist &mdash; it may have '
                 f'moved when the site was rebuilt.</p></div>'
                 f'<div class="section"><p class="dt" style="font-size:14px">'
                 f'<a href="{SITE_URL}" style="color:var(--gold)">Back to the '
                 f'homepage &rarr;</a></p></div>')
    (SITE / "404.html").write_text(
        shell("Page not found", "index.html", not_found, None, ""),
        encoding="utf-8")

    # Sitemap + robots. Every page written above, absolute, stamped with the
    # build date -- crawlers find the coach pages and write-ups on their own.
    pages = (["index.html", "standings.html", "records.html", "rules.html",
              "history.html", "coaches.html", "content.html"]
             + ["coach-%s.html" % cid for cid in roster]
             + [article_path(c) for c in content["content"] if c.get("article")])
    today = date.today().isoformat()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for pg in pages:
        loc = SITE_URL + ("" if pg == "index.html" else pg)
        sm.append("<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (loc, today))
    sm.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (SITE / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % SITE_URL,
        encoding="utf-8")

    n = len(roster)
    print("Built %d pages (%d coach profiles, %d write-ups), copied %d/%d media -> %s"
          % (8 + n + posts, n, posts, copied, total, SITE))


if __name__ == "__main__":
    main()
