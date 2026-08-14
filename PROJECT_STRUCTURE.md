# Pitch Saathi — project structure, explained

One page on what's where, and *why* it's organized this way — not just a
file listing. Written for learning, not just reference.

## The big idea behind the layout

Two different things eventually need this code:
1. **The real product** — a WhatsApp bot a PU actually messages.
2. **A browser demo** — for showing the concept to others before WhatsApp
   is connected.

Rather than build the "brains" (talk to Claude, transcribe audio, log to a
Sheet) twice, `src/` holds that logic ONCE, and both the demo and the real
WhatsApp entrypoint import from it. That single decision explains most of
the folder layout below.

## Folder by folder

### `src/` — the actual logic, reusable by both entrypoints
| File | What it does |
|---|---|
| `llm.py` | Every call to Claude lives here — the household roleplay, scoring, Ask-mode answers. |
| `stt.py` | Talks to Sarvam to turn a voice recording into text. |
| `tts.py` | Talks to Sarvam to turn Kiran Didi's feedback text into a spoken audio clip. |
| `sheets_logger.py` | Writes one row per session to the shared Google Sheet. |
| `state_store.py` | Remembers where each conversation currently is (a local JSON file, keyed by session/phone number). |
| `qa_bank.py` | Loads the सवाल-जवाब question bank and hands out questions. |
| `webhook.py`, `router.py`, `whatsapp.py` | The **real** WhatsApp entrypoint — not connected yet, but this is where a real PU's message would arrive and get routed. |

**Why separate from everything else**: this is the only code that talks to
Claude/Sarvam/Sheets. Keeping it in one place means fixing a prompt or a
scoring rule fixes it *everywhere it's used*, instead of two copies quietly
drifting apart.

### `demo/` — the browser stand-in for WhatsApp
`server.py` is a small Flask web server — it's what actually runs when you
type `python -m demo.server`, and it's what Render runs in production too.
`static/index.html` is the entire visible app: every screen, button, and
line of JavaScript, in one file. `server.py` just serves that file and
answers its `/api/...` calls using the `src/` modules above.

### `system_prompts/` — the app's actual words and knowledge
Not code — content. This is deliberately separate from `src/` so the
*personality and facts* can be edited without touching program logic.
| File | What it does |
|---|---|
| `practice.txt` | Instructions given to Claude for the household roleplay — persona, objections, scoring rules. |
| `sawal_jawab_questions.json` | The real question/answer pairs सवाल-जवाब quizzes on. |
| `motivation_nudges.md` | The short encouragement lines shown mid-conversation. |
| `feedback_opening_phrases.json` | The spoken/text opening lines for end-of-session feedback, picked by performance tier (excellent/good/improving). |
| `ask_*.txt`, `mera_madad.txt`, `vetted_curative_reference.txt` | Content for features not fully wired in yet. |

### `Input/` — raw source material, never uploaded to GitHub
Whenever you hand me a PDF, Word doc, or export to build real content
*from*, it goes here. It's listed in `.gitignore`, meaning **it never
reaches GitHub or Render** — on purpose, since it's scratch material for
me to read, not something the running app needs. (This distinction is
exactly what caused the सवाल-जवाब bug a few messages ago: the finished
JSON accidentally ended up in this never-uploaded folder instead of
`system_prompts/`.)

### `draft/` — new, just created: a home for loose reference files
Same idea as `Input/` — also gitignored, never uploaded — but for things
that aren't source material for me to build content from, just stuff
worth keeping around: old prototypes, interview notes, wireframe images.
Moving these here (instead of leaving them at the repo root) means they
can't accidentally get swept into a commit, and the root folder now only
shows things that are actually part of the app.

### `prototype/` — the design reference, kept on purpose
`Pitch_Saathi_HiFi_Prototype.html` is the original hi-fi mockup this whole
UI was rebuilt to match. Unlike `Input/`/`draft/`, this one **is** uploaded
to GitHub — it's a permanent record of the design this app is based on,
not disposable scratch material.

### `scripts/` — quick manual test tools
`console_test.py` and `voice_test.py` let a developer exercise the real
`src/` pipeline from a terminal — typing or speaking as the PU — without
opening a browser or needing WhatsApp connected. Not part of the app
itself, just a faster way to test it.

### `data/` — where the running app keeps its memory
`session_state.json` lives here once the app is running — gitignored,
since it's live scratch state for whoever's using it right now, not
something to save a history of.

## Root-level files

| File | Why it exists |
|---|---|
| `index.html` | The GitHub Pages landing page — a small page that links to the real, working app on Render. Not the app itself. |
| `render.yaml` | Tells Render.com exactly how to build and start the app when deploying. |
| `requirements.txt` | Every Python package the full project needs (including local-only dev tools). |
| `requirements-web.txt` | A trimmed version of the same list, used only for the Render deploy — leaves out packages the web app itself never imports. |
| `.env` / `.env.example` | `.env` holds your real secret API keys (never uploaded). `.env.example` is a template showing *which* keys are needed, with no real values — safe to upload. |
| `service_account.json` | Your real Google credentials file (never uploaded). |
| `.gitignore` | The exact list of files/folders that should never reach GitHub — secrets, `Input/`, `draft/`, local state. |
| `README.md` / `TOOLS_USED.txt` | Project documentation — currently a bit out of date after the recent rebuilds, worth a refresh at some point (not fixed in this pass). |

## On "backups" — you don't need a separate folder for this

You asked for a backup folder that keeps the older version whenever
something changes. You already have something better: **every `git
commit` already is that backup**, permanently, and none of them are ever
deleted or overwritten by a later change.

Concretely, your last few commits:
```
5da2cec  Prep for Render deployment + GitHub Pages landing page
9376eff  Add Sawal-Jawab (Knowledge Practice) as its own section...
f1f92f4  Fix objection spoilers, gendered address, Hinglish fallback...
641636e  Require explicit end-conversation tap before scoring...
```
Every one of those is a complete, permanent snapshot you can always go back
to — on GitHub.com (Commits → click any commit → click "Browse files" to
see the whole repo exactly as it was then), or locally. A manual backup
folder would just be a second, easily-outdated copy of what git is already
doing properly — it'd add clutter without adding real safety, since files
copied into a "backup" folder don't update themselves and are easy to
forget about.

If what you actually want is "let me get back to exactly how things were
on a specific day" — that's already possible any time, just ask me and
I'll show you the exact commit and how to restore from it.
