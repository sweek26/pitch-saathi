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
    Returns raw audio bytes (MP3). Raises SynthesisError on any failure -
    callers MUST catch this and fall back to text-only feedback; a TTS
    failure should never block the PU from seeing her feedback.

    output_audio_codec="mp3" matters a lot for low-network PUs: without it,
    Sarvam defaults to uncompressed WAV - measured a real feedback clip at
    1.5MB raw (2.1MB once base64-embedded in the response JSON, so the PU
    can't even see her TEXT feedback until that finishes downloading).
    Confirmed via a direct API test (not guessed) that this is the right
    field name - a same-text WAV-vs-mp3 comparison came back 136KB vs 47KB
    (65% smaller) and the mp3 response's bytes start with a real MPEG frame
    sync (0xFFF3...), not WAV's "RIFF" header. A same-named
    output_audio_format field is silently ignored by the API - do not
    "simplify" this back to that name, it looks equally plausible but does
    nothing.
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
            "output_audio_codec": "mp3",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SynthesisError(f"Sarvam TTS failed: {response.status_code} {response.text}")

    audios = response.json().get("audios")
    if not audios:
        raise SynthesisError("Sarvam TTS returned no audio")

    return base64.b64decode(audios[0])
