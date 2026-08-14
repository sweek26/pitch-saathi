"""
Test script — generates one sample audio clip per candidate Kiran Didi
feedback voice, using a real feedback-style sentence, so you can listen and
pick before we wire TTS into the actual app.

This is NOT part of the live app. Safe to delete after you're done.

Run from the project root (same place you run `python -m demo.server`):
    python scripts/tts_voice_test.py

Needs SARVAM_API_KEY in your .env (already set, per our earlier check).
Creates 4 .wav files in scripts/voice_samples/ — open each and play it.
"""
import os
import sys
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

import requests  # noqa: E402

API_KEY = os.environ["SARVAM_API_KEY"]

# A real feedback-style sentence — same length/tone as what practice_score_session
# actually produces (good + next_time + exact_phrase combined into one spoken line).
SAMPLE_TEXT = (
    "आपने शुरुआत बहुत अच्छी की और पूरे ध्यान से बात सुनी। अगली बार सेवा बताने से पहले "
    "उनकी ज़रूरत के बारे में एक सवाल पूछिए। आप ऐसे कह सकती हैं — आपको अभी बकरी के "
    "स्वास्थ्य में क्या परेशानी आ रही है।"
)

# Ishita shortlisted as the feedback voice. Sarvam's Bulbul v3 has no direct
# "softness/warmth" dial - the only tunable knob is `pace` (speech speed).
# Slowing it down is the closest lever to a gentler, more caring delivery.
# Generating both so you can compare normal vs slowed-down side by side.
VARIANTS = [
    {"label": "ishita_normal", "speaker": "ishita", "pace": 1.0},
    {"label": "ishita_soft", "speaker": "ishita", "pace": 0.85},
    {"label": "priya", "speaker": "priya", "pace": 1.0},
    {"label": "neha", "speaker": "neha", "pace": 1.0},
    {"label": "kavya", "speaker": "kavya", "pace": 1.0},
]

OUT_DIR = os.path.join(os.path.dirname(__file__), "voice_samples")
os.makedirs(OUT_DIR, exist_ok=True)

for variant in VARIANTS:
    print(f"Generating {variant['label']}...")
    resp = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": API_KEY, "Content-Type": "application/json"},
        json={
            "text": SAMPLE_TEXT,
            "language_code": "hi-IN",
            "speaker": variant["speaker"],
            "pace": variant["pace"],
            "model": "bulbul:v3",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  FAILED ({resp.status_code}): {resp.text[:300]}")
        continue
    audios = resp.json().get("audios", [])
    if not audios:
        print("  No audio returned in response.")
        continue
    audio_bytes = base64.b64decode(audios[0])
    out_path = os.path.join(OUT_DIR, f"{variant['label']}.wav")
    with open(out_path, "wb") as f:
        f.write(audio_bytes)
    print(f"  Saved: {out_path}  ({len(audio_bytes)} bytes)")

print("\nDone. Open scripts/voice_samples/ in File Explorer and play each file to compare.")
