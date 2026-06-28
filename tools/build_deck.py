#!/usr/bin/env python3
"""build_deck.py — render a pattern's walkthrough manifest into a self-contained,
deterministic HTML slide deck.

    python3 tools/build_deck.py [pattern_dir]     # default: patterns/cone-of-silence

Reads <pattern_dir>/walkthrough.py (WALKTHROUGH + DEMO_PROMPT) and writes
<pattern_dir>/deck.html. A PURE function of the manifest — no Date/random, a fixed demo
prompt, frozen output — so the deck is byte-identical on every run and on every machine,
and the single .html file opens standalone in any browser (nothing external to fetch).
"""
import html
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
pattern_dir = (Path(sys.argv[1]) if len(sys.argv) > 1
               else REPO / "patterns" / "cone-of-silence").resolve()
sys.path.insert(0, str(pattern_dir))
import walkthrough as wt  # noqa: E402

PROMPT = wt.DEMO_PROMPT
ACT_TITLES = {
    ("engaged", "read"):      "Cone ENGAGED · Read the secret",
    ("engaged", "detect"):    "Cone ENGAGED · Detect cleartext",
    ("disengaged", "read"):   "Cone DISENGAGED · Read the secret",
    ("disengaged", "detect"): "Cone DISENGAGED · Detect cleartext",
}


def esc(s): return html.escape(s, quote=False)
def br(s):  return esc(s).replace("\n", "<br>")


def beat_html(b):
    if "title" in b:
        return (f'<div class="beat title"><h1>{esc(b["title"])}</h1>'
                f'<p class="tagline">{esc(b["tagline"])}</p>'
                f'<p class="kicker">{esc(b.get("kicker", ""))}</p></div>')
    if "say" in b:
        return f'<div class="beat"><p class="say">{br(b["say"])}</p></div>'
    if "prose" in b:
        return f'<div class="beat"><p class="prose">{br(b["prose"])}</p></div>'
    if "cmd" in b:
        return ('<div class="beat"><div class="term">'
                f'<div class="promptline"><span class="prompt">{esc(PROMPT)}</span>'
                f'<span class="cmd">{esc(b["cmd"])}</span></div>'
                f'<pre class="out">{esc(b["out"])}</pre></div></div>')
    if "verdict" in b:
        return f'<div class="beat"><p class="verdict {"ok" if b["ok"] else "fail"}">{esc(b["verdict"])}</p></div>'
    if "html" in b:
        return f'<div class="beat">{b["html"]}</div>'
    return ""


def slide_html(title, items):
    head = f'<h2 class="slide-title">{esc(title)}</h2>' if title else ""
    return f'<section class="slide">{head}{"".join(beat_html(b) for b in items)}</section>'


# --- narrative order: title -> problem -> engage -> 2 acts -> disengage -> 2 acts -> takeaway
slides = [
    (None, [{"title": "The Cone of Silence",
             "tagline": "a low-effort, RAM-only zone your secret never leaves",
             "kicker": "legacy-secrets-adapters · a walkthrough"}]),
    ("The problem", [{"prose":
        "A legacy app reads its credentials from a plaintext file on disk — and won't be "
        "re-released. Anyone who reads the disk (a backup, an image layer, a stray git add, "
        "a stolen drive) reads the password. We fix it WITHOUT touching the app."}]),
    ("Engage the Cone", [
        {"say": "Decrypt the secret into a RAM-backed file at the path the app already reads."},
        {"cmd": "./cone.py engage",
         "out": f"→ Cone ENGAGED: secret decrypted into RAM at {wt.SECRET} (mode 0400)"}]),
    (ACT_TITLES[("engaged", "read")],     wt.WALKTHROUGH[("engaged", "read")]),
    (ACT_TITLES[("engaged", "detect")],   wt.WALKTHROUGH[("engaged", "detect")]),
    ("Disengage the Cone", [
        {"say": "Wipe the secret from RAM. On disk there was only ciphertext all along."},
        {"cmd": "./cone.py disengage",
         "out": "→ Cone DISENGAGED: plaintext wiped from RAM (a reboot wipes /dev/shm anyway)"}]),
    (ACT_TITLES[("disengaged", "read")],   wt.WALKTHROUGH[("disengaged", "read")]),
    (ACT_TITLES[("disengaged", "detect")], wt.WALKTHROUGH[("disengaged", "detect")]),
    ("The takeaway", [
        {"prose": "The secret is never stored in the clear — only briefly present, in RAM, while "
                  "the app needs it. On disk: ciphertext. In RAM: gone on power-off. The app never changed."},
        {"prose": "In production the Cone is a systemd RuntimeDirectory tmpfs, and the key never "
                  "touches disk — sealed to the machine's TPM, or handed over by OpenBao."},
        {"html": '<p class="prose">More in <code>enlighten.html</code> &nbsp;·&nbsp; '
                 '<a href="https://github.com/Wave-Engineering/legacy-secrets-adapters">the catalog</a></p>'}]),
]

SECTIONS = "\n".join(slide_html(t, items) for t, items in slides)

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Cone of Silence — a walkthrough</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; height: 100vh; overflow: hidden; background: #0d1117; color: #e6edf3;
         font: 18px/1.6 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .slide { position: absolute; inset: 0; display: none; flex-direction: column; justify-content: center;
           gap: 1rem; max-width: 940px; margin: 0 auto; padding: 4rem 2rem 5rem; }
  .slide.active { display: flex; }
  .slide-title { margin: 0 0 .5rem; font-size: 1.5rem; color: #7ee787; font-weight: 700; }
  .beat { opacity: 0; transform: translateY(12px); transition: opacity .45s ease, transform .45s ease; }
  .beat.show { opacity: 1; transform: none; }
  .say { color: #b9c2cc; margin: .2rem 0; }
  .prose { color: #c9d1d9; margin: .4rem 0; font-size: 1.12rem; }
  .title { text-align: center; }
  .title h1 { font-size: 3rem; margin: 0 0 .4rem; line-height: 1.1; }
  .tagline { font-size: 1.35rem; color: #7ee787; margin: 0; }
  .kicker { color: #8b949e; font-family: "SF Mono", Consolas, monospace; margin-top: 1.2rem; }
  .term { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: .8rem 1rem;
          font-family: "SF Mono", "JetBrains Mono", Consolas, monospace; font-size: .92rem; margin: .3rem 0; }
  .promptline { white-space: pre-wrap; word-break: break-all; }
  .prompt { color: #7ee787; } .cmd { color: #e6edf3; }
  .term pre.out { margin: .5rem 0 0; color: #c9d1d9; white-space: pre-wrap; word-break: break-word; }
  .verdict { font-weight: 700; margin: .4rem 0; }
  .verdict.ok { color: #7ee787; } .verdict.fail { color: #ff7b72; }
  a { color: #58a6ff; } code { font-family: "SF Mono", Consolas, monospace; color: #a5d6ff; }
  .hud { position: fixed; bottom: 1rem; left: 0; right: 0; display: flex; justify-content: center;
         gap: 1rem; align-items: center; color: #8b949e; font-size: .8rem; }
  .hud .bar { width: 180px; height: 4px; background: #21262d; border-radius: 2px; overflow: hidden; }
  .hud .bar > i { display: block; height: 100%; background: #7ee787; transition: width .3s ease; }
  kbd { background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 0 .35rem; }
</style>
</head>
<body>
__SECTIONS__
<div class="hud">
  <span id="counter">1 / 1</span>
  <span class="bar"><i id="prog"></i></span>
  <span><kbd>←</kbd> <kbd>→</kbd> / click to navigate</span>
</div>
<script>
  const slides = [...document.querySelectorAll('.slide')];
  let si = 0;
  const beats = s => [...s.querySelectorAll('.beat')];
  const shownCount = s => beats(s).filter(b => b.classList.contains('show')).length;

  function hud() {
    document.getElementById('counter').textContent = (si + 1) + ' / ' + slides.length;
    document.getElementById('prog').style.width = ((si + 1) / slides.length * 100) + '%';
  }
  function enter(i, revealAll) {
    slides.forEach((s, k) => s.classList.toggle('active', k === i));
    si = i;
    const bs = beats(slides[i]);
    bs.forEach(b => b.classList.remove('show'));
    if (revealAll) bs.forEach(b => b.classList.add('show'));
    else if (bs.length) bs[0].classList.add('show');
    hud();
  }
  function next() {
    const bs = beats(slides[si]), shown = shownCount(slides[si]);
    if (shown < bs.length) bs[shown].classList.add('show');
    else if (si < slides.length - 1) enter(si + 1, false);
  }
  function prev() {
    const shown = shownCount(slides[si]);
    if (shown > 1) beats(slides[si])[shown - 1].classList.remove('show');
    else if (si > 0) enter(si - 1, true);
  }
  addEventListener('keydown', e => {
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); next(); }
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); prev(); }
    else if (e.key === 'Home') enter(0, false);
    else if (e.key === 'End') enter(slides.length - 1, true);
  });
  addEventListener('click', e => { if (!e.target.closest('a')) next(); });
  enter(0, false);
</script>
</body>
</html>
"""

out = TEMPLATE.replace("__SECTIONS__", SECTIONS)
deck = pattern_dir / "deck.html"
deck.write_text(out)
print(f"wrote {deck.relative_to(REPO)} ({len(out)} bytes, {len(slides)} slides)")
