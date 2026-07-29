"""
Speech-to-text via Sarvam AI, tuned for Hindi/Avadhi-inflected voice notes.

Swap this module if Sarvam's confidence on Avadhi turns out too low in
testing — AI4Bharat IndicASR was the fallback flagged in the PRD.
"""
import os
import requests

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


class TranscriptionError(Exception):
    """Sarvam couldn't transcribe this audio - caller decides how to recover
    (e.g. ask the PU to resend a shorter voice note)."""


class AudioTooLongError(TranscriptionError):
    """Sarvam's synchronous endpoint hard-caps audio at 30 seconds."""


def transcribe(audio_bytes, mime_type="audio/ogg"):
    """
    Returns {"text": str, "confidence": float | None}.
    Raises AudioTooLongError if the clip exceeds Sarvam's 30-second limit,
    or TranscriptionError for any other API failure.
    """
    api_key = os.environ["SARVAM_API_KEY"]
    response = requests.post(
        SARVAM_STT_URL,
        headers={"api-subscription-key": api_key},
        files={"file": ("audio.ogg", audio_bytes, mime_type)},
        data={"language_code": "hi-IN"},
        timeout=30,
    )
    if response.status_code != 200:
        if "exceeds the maximum limit" in response.text:
            raise AudioTooLongError(response.text)
        raise TranscriptionError(f"Sarvam STT failed: {response.status_code} {response.text}")

    result = response.json()
    return {
        "text": result.get("transcript", ""),
        "confidence": result.get("confidence"),  # log low-confidence transcripts for review, per PRD
    }
