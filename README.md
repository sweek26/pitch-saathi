# Pitch Saathi

Pilot for 5–10 Pashu Udhyami (PU). Two modules — **Practice** (AI plays the
household, scores against the rubric, tags Knowledge vs Confidence) and
**Mera Madad** (personal weak-spot recap from her own history). Full spec:
`Pitch_Saathi_Context_Handoff.md` one level up in `Training and Learning/`.

## Stack

| Piece | Tool | Why |
|---|---|---|
| Delivery | Browser app (Flask + vanilla JS) | Reachable via a link — no messaging platform needed |
| Speech-to-Text | Sarvam AI | Built for Indian languages/dialects incl. Hindi |
| LLM | Claude (Anthropic) | Two independent system prompts, no fine-tuning needed |
| Logging | Google Sheets (gspread) | Matches "shared spreadsheet, no DB" scale |
| State | Local JSON file (`data/session_state.json`, gitignored) | No DB per spec — fine for 5–10 PU |

## Setup

1. `pip install -r requirements.txt`
2. `cp .env.example .env` and fill in real values (never commit `.env`):
   - Sarvam: sign up at sarvam.ai → API key.
   - Anthropic: console.anthropic.com → API key.
   - Google Sheets: create a Google Cloud service account, enable the
     Sheets API, download its JSON key as `service_account.json` in this
     folder, then share your target Sheet with that service account's
     email (Editor access). Copy the Sheet's ID from its URL into
     `GOOGLE_SHEET_ID`.
3. In row 1 of that Sheet, add these exact headers (matches what
   `sheets_logger.py` reads/writes):
   `phone_number | timestamp | module | scenario | transcript | transcript_confidence | introduction | rapport | service | gap_tag | reply_text`

## Running the app

`python -m demo.server` then open `http://localhost:5050` — this is the
actual pilot: a browser-based chat app with onboarding (name +
panchayat), Practice, and Mera Madad. It's also what Render runs in
production. Includes an **"Ask — Test Mode"** screen for internally
comparing three approaches to answering technical/medical questions
(safe-default / vetted-retrieval / experimental-generation) — this is
explicitly a team-evaluation tool, not part of what a PU sees, and isn't
wired into the main app flow.

Two lighter-weight dev tools exercise the same underlying
`llm.py`/`stt.py`/`sheets_logger.py` code from a terminal, without
opening a browser:

- `python -m scripts.console_test` — type as the PU in a terminal,
  fastest way to test prompt/scoring behavior.
- `python -m scripts.voice_test` — speak into your mic, get real Sarvam
  transcription + a reply.

## About the earlier WhatsApp exploration

A WhatsApp channel was explored early in this project. That entrypoint
code (`webhook.py`, `router.py`, `whatsapp.py`) is retired to `draft/`
(gitignored) and isn't part of the current app — the browser app above
is the pilot PUs actually use.

## Design assumptions — please review

The build spec didn't fully define these; I picked defaults so the
pipeline is runnable. Flag anything you want changed:

1. **Module/scenario selection** — done via tappable buttons/chips in
   the browser UI, not typed keywords. Matches the low-literacy,
   voice-first design intent. (Originally prototyped against WhatsApp's
   button messages; that entrypoint is retired to `draft/`.)
2. **Practice session end trigger** — auto-scores and ends after 5 PU
   voice notes (`router.py: MAX_PRACTICE_TURNS`). No explicit "I'm done"
   signal exists yet. Easy to swap for a keyword-based end instead.
3. **Conversation state** — a local JSON file keyed by phone number
   (`src/state_store.py`), not a database, per spec. Won't survive past
   this pilot's scale.

## Non-negotiables already built in

- PU only ever sees `pu_feedback_hindi` / the Mera Madad reply text — raw
  scores and gap tags go to the Sheet only, never to the PU.
- Practice and Mera Madad load separate prompt files
  (`system_prompts/practice.txt`, `system_prompts/mera_madad.txt`) and are
  never combined in one LLM call.
- The persona is instructed to never supply real medical/technical
  answers even in character — it defers to "ask your Field Executive."

## Not yet built

- PU consent flow / enrollment.
- Low-confidence transcript review queue (Sarvam returns a confidence
  score; it's logged per row but nothing acts on it yet).
