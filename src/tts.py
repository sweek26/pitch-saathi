"""
Text-to-speech via Sarvam AI (Bulbul v3) - Kiran Didi's spoken feedback.

Sibling module to stt.py; same account, same SARVAM_API_KEY, no new secret.
"""
import base64
import os
import requests

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
KIRAN_VOICE = "ishita"
KIRAN_PACE = 0.85


class SynthesisError(Exception):
    """Sarvam couldn't synthesize this text - caller falls back to text-only."""


def synthesize(text, speaker=KIRAN_VOICE, pace=KIRAN_PACE):
    """
    Returns raw audio bytes (WAV). Raises SynthesisError on any failure -
    callers MUST catch this and fall back to text-only feedback; a TTS
    failure should never block the PU from seeing her feedback.
    """
    api_key = os.environ["SARVAM_API_KEY"]
    response = requests.post(
        SARVAM_TTS_URL,
        headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "language_code": "hi-IN",
            "speaker": speaker,
            "pace": pace,
            "model": "bulbul:v3",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SynthesisError(f"Sarvam TTS failed: {response.status_code} {response.text}")

    audios = response.json().get("audios")
    if not audios:
        raise SynthesisError("Sarvam TTS returned no audio")

    return base64.b64decode(audios[0])
