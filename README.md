# Pitch Saathi — WhatsApp Test Pipeline

Pilot for 5–10 Pashu Udhyami (PU). Two modules — **Practice** (AI plays the
household, scores against the rubric, tags Knowledge vs Confidence) and
**Mera Madad** (personal weak-spot recap from her own history). Full spec:
`Pitch_Saathi_Context_Handoff.md` one level up in `Training and Learning/`.

## Stack

| Piece | Tool | Why |
|---|---|---|
| Messaging | WhatsApp Cloud API (Meta) | Free sandbox tier, official |
| Speech-to-Text | Sarvam AI | Built for Indian languages/dialects incl. Hindi |
| LLM | Claude (Anthropic) | Two independent system prompts, no fine-tuning needed |
| Logging | Google Sheets (gspread) | Matches "shared spreadsheet, no DB" scale |
| State | Local JSON file (`data/session_state.json`, gitignored) | No DB per spec — fine for 5–10 PU |

## Setup

1. `pip install -r requirements.txt`
2. `cp .env.example .env` and fill in real values (never commit `.env`):
   - WhatsApp: create a Meta for Developers app → WhatsApp product → copy
     Phone Number ID + a temporary access token. Pick any string for
     `WHATSAPP_VERIFY_TOKEN` yourself.
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

## Testing without WhatsApp (current default — WhatsApp isn't connected yet)

Three ways to exercise the real pipeline (same `llm.py`/`stt.py`/`sheets_logger.py`
code the WhatsApp path will use) without needing WhatsApp at all:

- `python -m scripts.console_test` — type as the PU in a terminal, fastest
  way to test prompt/scoring behavior.
- `python -m scripts.voice_test` — speak into your mic, get real Sarvam
  transcription + a reply. Closest thing to the real experience.
- `python -m demo.server` then open `http://localhost:5050` — a
  browser-based WhatsApp-style chat demo with onboarding (name +
  panchayat), Practice, and Mera Madad. Good for showing the concept to
  others. Includes an **"Ask — Test Mode"** screen for internally
  comparing three approaches to answering technical/medical questions
  (safe-default / vetted-retrieval / experimental-generation) — this is
  explicitly a team-evaluation tool, not part of the real product, and
  is not wired into `router.py`/`webhook.py`.

## Run against real WhatsApp (once connected)

```
python -m src.webhook
ngrok http 5000
```

Put the ngrok HTTPS URL + `/webhook` into the Meta app's webhook config,
with the same verify token as `.env`. Subscribe to the `messages` field.

## Design assumptions — please review

The build spec didn't fully define these; I picked defaults so the
pipeline is runnable. Flag anything you want changed:

1. **Module/scenario selection** — done via WhatsApp button messages
   (`src/whatsapp.py: send_module_menu`, `send_scenario_menu`), not typed
   keywords. Matches the low-literacy, voice-first design intent.
2. **Practice session end trigger** — auto-scores and ends after 5 PU
   voice notes (`router.py: MAX_PRACTICE_TURNS`). No explicit "I'm done"
   signal exists yet. Easy to swap for a keyword-based end instead.
3. **Conversation state** — a local JSON file keyed by phone number
   (`src/state_store.py`), not a database, per spec. Won't survive past
   this pilot's scale.

## Non-negotiables already built in

- PU only ever sees `pu_feedback_hindi` / the Mera Madad reply text — raw
  scores and gap tags go to the Sheet only, never to WhatsApp.
- Practice and Mera Madad load separate prompt files
  (`system_prompts/practice.txt`, `system_prompts/mera_madad.txt`) and are
  never combined in one LLM call.
- The persona is instructed to never supply real medical/technical
  answers even in character — it defers to "ask your Field Executive."

## Not yet built

- WhatsApp itself isn't connected yet — decision pending on a fresh Meta
  Developer app vs. the org's existing Gupshup/Glific WhatsApp setup.
- PU consent flow / enrollment.
- Low-confidence transcript review queue (Sarvam returns a confidence
  score; it's logged per row but nothing acts on it yet).
- `router.py`'s module-selection flow doesn't yet have the name/panchayat
  onboarding the demo app prototypes — deferred until it's testable
  against real WhatsApp messages.
