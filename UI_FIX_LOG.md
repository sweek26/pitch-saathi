# UI fix log — 2026-08-13

## Update — onboarding illustration position/size + heading spacing

Before touching anything, I re-read the live file and found it had already
changed since the log above: `.onboard-hero`'s position was being held with
`margin: -200px auto 0`, and `.onboard-divider`'s `gap` had become
`10000px`. That gap value was pushing the divider's two short lines
completely off-screen (rendering at x≈−9822 and x≈10182 — confirmed by
measuring their `getBoundingClientRect()`), so the divider was visibly
showing only its centre dot with no lines on either side. This was already
happening before my edit, independent of anything requested here.

**File touched:** only `demo/static/index.html` again — same as before, no
backend/API changes.

- `.onboard-hero` (line 131): replaced the `-200px` margin hack with a
  proper `margin: 0 auto` plus
  `transform: translateY(-8px) scale(1.12); transform-origin: center top;`.
  `transform` is paint-only — it doesn't add to the layout's height budget
  the way a margin change would, so the enlarge+move-up was free to do
  without disturbing anything below it. Verified: image now renders at
  224×167px (was 200×150 — a +12% increase, aspect ratio intact, confirmed
  by comparing width:height ratios before/after), centred within 0.01px of
  the viewport centre, with 6.7px of clear space above it before the header.
  Picked `-8px` (not the fuller `-16px` I tried first) because `-16px`
  measured out to only ~2px of header clearance — too fragile across
  devices/font-loading timing, so I dialed it back once I measured the real
  number instead of trusting the arithmetic.
- Added a `@media (max-height: 630px)` rule right under it (new, lines
  132–134): on short viewports, it drops the `translateY` and keeps only
  the `scale`. Reason: I tested 320×568 and found the image overlapping the
  header by ~18px *even with the transform completely removed* — this
  screen's existing content (padding, gaps, and the already-large field
  label size/margins at lines 128–129 — `1.1rem` font, `20px`/`15px`
  margins, which this request didn't ask me to touch) is simply taller than
  a 568px-tall viewport has room for, regardless of my change. The media
  query stops my move-up effect from making that pre-existing overlap
  worse; it doesn't fix the pre-existing overlap itself, since that would
  mean changing the label sizing this request explicitly excluded.
  **Flagging this for you** — if you test on a short device (568px-tall
  viewport, e.g. an older/smaller phone) and see the illustration crowding
  the header, that's this pre-existing issue, not something introduced now.
- `.onboard-headline` margin-top (line 136): `5px → 20px`, to keep the
  illustration→heading gap comfortable (18px, measured) now that less of
  it comes free from the transform than my first attempt assumed.
- `.onboard-divider` (line 137): `gap: 10000px → 8px` (the fix for the
  off-screen lines above) and `margin: 6px 0 5px → 6px 0 6px`. Combined
  with the headline change, heading→"अपना नाम लिखें" gap is now 33px
  (measured), up from the ~11px it would have been at the pre-existing
  correct gap value.

**Not changed, confirmed by reading the diff:** header, Hindi text/wording,
input fields, mic icons, colours, borders, `.fieldlbl` font-size/margins,
screen dimensions, any other screen's CSS.

**Tested:** 360×640 (primary target) — 0 scroll overflow, image
224×167px/centred/6.7px header clearance/18px+33px gaps, all Hindi text and
icons present via `get_page_text`, no console or server errors. Also
checked 320×568 and 360×600 (both trigger the media query — clearance
matches the pre-existing baseline, not worse) and 360×660 (above the media
query threshold — full effect applies, 15.7px clearance).

Every change in this round, in one file: [demo/static/index.html](demo/static/index.html).
No other file was touched — no backend, API, AI/prompt, or STT logic changed.
Line numbers below are the **current** line numbers in that file, after all
these edits landed (so you can open the file and jump straight to them).

---

## 1. Unexpected "।" while typing

**Investigated first, per your instructions, before writing any fix:**
- Grepped the entire repo for `।`. Every occurrence inside `index.html` is
  static Hindi sentence text that's supposed to be there (error messages,
  safety notices, prep text) — e.g. line 353 `"...कोई बात नहीं।"`, line 681
  `"...अनुमति नहीं मिली।"`. None of them sit near the name/GP inputs.
- Grepped for every `addEventListener`/`oninput`/`onkeyup`/`onkeypress` in
  the file. There is exactly **one**, at line 513 — the Enter-key listener
  that clicks the submit button. It only reads `e.key`, never touches the
  input's value. Nothing else in the file writes to `onboardNameInput` or
  `onboardGpInput`.
- Checked `src/stt.py` and the `/api/onboard/transcribe` route in
  `demo/server.py` (lines 135–150) in case this was a transcription
  artifact. Confirmed it's an unmodified pass-through to `stt.transcribe()`
  with no punctuation logic — and irrelevant anyway, since **manual typing
  never calls this endpoint at all** (no network request fires while you type).

**Conclusion:** the danda isn't coming from our code — backend, frontend,
or STT. This matches a well-known behaviour of Hindi virtual
keyboards/IMEs (e.g. Gboard's Hindi mode mapping "." or a double-space to
"।" automatically), which happens at the OS/keyboard level, outside what
this webpage can see or control. Telling you this clearly, as you asked,
before making any change.

**What I changed anyway:** since "।" can never legitimately belong in a
person's name or a gram panchayat name, I added a small live sanitizer that
strips it the instant it appears — a real code fix (not a CSS mask), scoped
only to these two fields:

- `demo/static/index.html:519–528` — new function `stripStrayDanda(inp)`:
  listens for the `input` event, and if the field's value contains "।", it
  removes it and re-places the cursor correctly.
- `demo/static/index.html:529–530` — wires it to `onboardNameInput` and
  `onboardGpInput` only. No other field is affected.

```js
function stripStrayDanda(inp) {
  inp.addEventListener("input", () => {
    if (!inp.value.includes("।")) return;
    const pos = inp.selectionStart;
    const removedBeforeCursor = (inp.value.slice(0, pos).match(/।/g) || []).length;
    inp.value = inp.value.replace(/।/g, "");
    const newPos = Math.max(0, pos - removedBeforeCursor);
    inp.setSelectionRange(newPos, newPos);
  });
}
stripStrayDanda(document.getElementById("onboardNameInput"));
stripStrayDanda(document.getElementById("onboardGpInput"));
```

Tested: typing (simulated) `सुनीता।` and `सुनीता। गुप्ता` both come out as
`सुनीता` / `सुनीता गुप्ता` — danda gone, rest of the text and cursor position
untouched.

---

## 2. No gap between Home Section 1 and Section 2

Section 1 = the "बातचीत का अभ्यास" card, Section 2 = the "सवाल-जवाब" card —
both `.fcard` elements inside `#screen-home`.

- `demo/static/index.html:74` — added one new, Home-scoped rule:
  ```css
  .home-picker .fcard + .fcard { margin-top: 24px; }
  ```
  This targets *only* an `.fcard` that immediately follows another `.fcard`
  inside `.home-picker` — i.e. only Section 2, only on the Home screen.
  It does not touch `.fcard`'s own shared `margin-bottom: 10px` (line 73),
  so the gap *below* Section 2 (before the "बदलें" link) stays exactly as
  it was. Nothing inside either card changed.
- To keep this from causing scrolling, I trimmed the same amount back out
  of the *outer* Home spacing (not card-internal spacing):
  - `demo/static/index.html:70` — `.home-picker` bottom padding 16px → 6px
  - `demo/static/index.html:71` — `.section-head` margin 10px/12px → 8px/7px

Measured result: gap between the two cards is now exactly **24px**
(measured via bounding boxes), the gap below Section 2 is unchanged at
**10px**, and the Home screen still has **zero scroll overflow** at
360×640 and 320×568.

*(First attempt used `.fcard:first-child`, which doesn't match here since
the greeting bubble is the actual first child — caught this in testing
before shipping it, corrected to the `+` sibling selector above.)*

---

## 3. Onboarding image size + "अपना नाम लिखें" text size

You asked to make the hero illustration bigger and the field-label text
bigger. Both are on the onboarding/login screen (`#screen-onboarding`).

- `demo/static/index.html:131` — `.onboard-hero`: `max-width`/`max-height`
  195×134px → **200×180px** (renders at 200×150 once the image's own aspect
  ratio is applied).
- `demo/static/index.html:128` — `.fieldlbl` (covers both "अपना नाम लिखें"
  and "अपनी ग्राम पंचायत लिखें", since they share this one class):
  `font-size` 0.85rem → **0.95rem**.

Growing those two elements needed ~50px more vertical room than the screen
had to spare, so I trimmed the *spacing* around them by the same amount
(not any text or button size) — all on lines 127–139:
  - `.onboarding` padding 16px→12px, gap 10px→5px
  - `.onboard-headline` top margin 8px→5px
  - `.onboard-divider` margin 8/6px → 6/5px
  - `.fieldrow + .fieldrow` margin 10px→7px
  - `#onboardSubmit` (line 208) top margin 18px→10px

Measured result: onboarding screen is still **zero scroll overflow** at
360×640, with the bigger image and bigger labels both rendering correctly.

---

## 4. Mic icon colour consistency

The two small mic buttons inside the name/GP fields used two different
colours (purple `#6C4FC4` and pink `#D63C6E`) — inconsistent with each
other and with the big brown mic button used everywhere else in the app
(practice screen, सवाल-जवाब screen).

- `demo/static/index.html:150–156` — removed the `.mic-inset.purple` /
  `.mic-inset.pink` rules; `.mic-inset` itself now carries `color:
  var(--brown)` directly, so every inset mic is brown by default. The
  `.recording` state (turns red while actively recording) is unchanged —
  that's a status signal, not a decorative colour.
- `demo/static/index.html:250` and `:261` — removed the now-unused
  `purple`/`pink` classes from the two `<button class="mic-inset ...">`
  elements in the HTML.

Every mic icon in the app (both onboarding fields, the practice screen,
and the सवाल-जवाब screen) now renders the same brown used for buttons and
headings elsewhere — confirmed by reading each button's computed color
after the change (all three: `rgb(105, 61, 48)`).

---

## Files modified this round

Only **[demo/static/index.html](demo/static/index.html)**. Confirmed
unchanged: `demo/server.py`, everything in `src/`, everything in
`system_prompts/`, `render.yaml`, `.gitignore`. No navigation function was
added, removed, or rewired — `go()`, `selectPtype()`, `startQa()`,
`openQaServices()` all work exactly as before.

## How to test locally

1. Run the app: `python -m demo.server` (or use whatever you normally run
   it with) and open `http://localhost:5050`.
2. **Danda fix**: go to the name/GP entry screen and type — if your
   keyboard ever inserts "।", it will disappear immediately as you type,
   without affecting the rest of what you typed.
3. **Home gap**: go to the Home screen and look at the space between the
   "बातचीत का अभ्यास" card and the "सवाल-जवाब" card — visibly larger than
   the space below either card.
4. **Image/text size**: on the name/GP entry screen, the illustration and
   the two field labels are visibly larger than before.
5. **Mic colour**: the two mic icons inside the name/GP fields are now the
   same brown as each other (and as the big mic button on the practice
   and सवाल-जवाब screens).
6. Confirm nothing else moved: Home cards' chips still jump straight into
   practice/सवाल-जवाब, tapping a card body still opens the full picker,
   and the "बदलें" link still returns to this screen with your saved name/GP.
