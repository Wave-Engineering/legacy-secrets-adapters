# Cone of Silence demo — backlog

Polish/feature items for `demonstrate.py` (and the demo framework). Captured to discuss
and implement **one at a time** — do not batch. Becomes GitHub issues at repo-migration time.

- [x] **1. Clear screen at the top-level menu.** _(done)_
  On return to the top-level menu, `clear`/`cls` (or equivalent) so the screen is uncluttered
  and the user doesn't feel cramped by scrollback.
  _Implemented: `clear_screen()` (TTY-only ANSI `\033[H\033[2J\033[3J`); called at loop top.
  Moved the per-walkthrough pause to one uniform "press enter to return" after every action so
  output (incl. engage/disengage confirmations) lingers until acknowledged, then the screen wipes._

- [x] **2. "In progress" state on the experience block.**
  When the user engages/disengages for the first time, mark that state's experience block as
  *in progress* (a distinct indicator) until they actually complete both **3) Read** and
  **4) Detect** in that state — only then is it "done."
  _touches: the `seen` tracking + checkbox rendering; today it marks done on a single 3-or-4._

- [x] **3. Vertical whitespace around the fake prompt.**
  Add blank lines above and below a shown prompt in a walkthrough so it stands out / is set off.
  _touches: `shell()`._

- [x] **4. Full-left-justify the fake prompt.**
  The fake prompt is currently indented like the walkthrough text, but the CLI output is
  full-left. Left-justify the prompt too, so prompt + output read as one contiguous terminal block.
  _touches: `shell()` (drop the leading indent on the prompt line)._

- [x] **5. Distinct color for prompt + output; optional syntax highlighting.**
  Render the fake prompt and the command output in regular/default terminal color, distinct from
  the walkthrough narration color. If feasible, also pipe command output through a highlighter
  (e.g. `bat`, `pygmentize`, `highlight`) for syntax coloring.
  _touches: `shell()` / `coach()` color scheme; output piping is a sub-task._

- [ ] **6. Abstract into a JSON-driven demonstration app. (DEFER until pattern #2.)**
  Once there's more than one pattern walkthrough, factor the experience into a generic
  demonstration app driven by per-pattern JSON files (menu, walkthrough steps, commands, copy).
  Do this when we tackle the second pattern, not before.
  _touches: new framework module + `*.demo.json`; current `demonstrate.py` becomes the engine._

---

## Agreed design — ready to implement (2026-06-28)

- **2. progress:** per-side track {read, detect}. Glyphs `[ ]` → `[~]` (visited / one done) →
  `[✓]` (both done). Engage/disengage flips that side to `[~]`. `6) Finish` requires BOTH sides
  `[✓]` (i.e. all four walkthroughs experienced).
- **3. whitespace:** blank line above the prompt and below the command *output* — frame the whole
  prompt+output block. NO blank between the prompt and its own output.
- **4. justify:** prompt + output flush at column 0; narration stays indented
  (indented = coaching, flush-left = the machine).
- **5. color:** narration dim + indented; terminal block default color (prompt keeps real PS1
  colors). Best-effort highlighting, no hard dependency: `ls`/`grep` get `--color=always`,
  `cat secrets.json` routes through `bat -l json` if `bat` exists, else plain `cat`.
- **6. abstraction (DEFERRED to pattern #2):** engine (clear/coach/shell/prompt/menu/progress) +
  per-pattern JSON manifest (steps as `{narration, command, state}`) + thin mechanics-hook module.
  Keep UI primitives separated from Cone-specific actions now so the later split is mechanical.
