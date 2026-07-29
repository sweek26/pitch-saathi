"""
Local voice test — speak into your microphone as the PU, get transcribed by
Sarvam, then get the household persona's reply. Same real pipeline as
WhatsApp will use (voice in, text out), just without WhatsApp.

Run from the project root:
    python -m scripts.voice_test
"""
import os
import sys
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

from src import llm, sheets_logger, stt  # noqa: E402

SAMPLE_RATE = 16000
TEST_PHONE = "CONSOLE_TEST_919999999999"
TMP_WAV = os.path.join(os.path.dirname(__file__), "..", "data", "_voice_test_tmp.wav")


def record_until_enter():
    frames = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
        input()  # recording runs in the background until you press Enter

    audio = np.concatenate(frames, axis=0) if frames else np.zeros((0, 1), dtype="int16")
    with wave.open(TMP_WAV, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(audio.tobytes())
    return TMP_WAV


def run_practice_voice():
    print("\nScenario? 1 = Basic pitch, 2 = Price objection")
    scenario = "basic_pitch" if input("> ").strip() == "1" else "price_objection"

    turns = []
    print("\nHar turn: Enter dabaiye, bolna shuru kijiye, khatam hone par Enter dabaiye phir se.")
    print("Conversation khatam karne ke liye, bol dijiye 'end'.\n")

    while True:
        input("[Bolne ke liye Enter dabaiye]")
        print("Recording... (bol kar khatam hone par Enter dabaiye)")
        path = record_until_enter()

        with open(path, "rb") as f:
            audio_bytes = f.read()
        os.remove(path)

        result = stt.transcribe(audio_bytes)
        print(f"\nAapne bola (transcript): {result['text']}")
        if result.get("confidence") is not None:
            print(f"(confidence: {result['confidence']})")

        if not result["text"].strip():
            print("Kuch transcribe nahi hua — shayad bahut chhota ya chup rahi recording thi. Dobara try kijiye.\n")
            continue

        words = [w.strip(".।,!?").lower() for w in result["text"].strip().split()]
        if any(w in ("end", "एंड", "इंड") for w in words):
            break

        turns.append({"role": "user", "text": result["text"]})
        reply = llm.practice_persona_reply(scenario, turns)
        turns.append({"role": "assistant", "text": reply})
        print(f"\nHousehold> {reply}\n")

    if not turns:
        print("Koi turn record nahi hua, scoring skip kar rahe hain.")
        return

    score = llm.practice_score_session(scenario, turns)
    print("\n--- Feedback (jo PU ko dikhega) ---")
    print(score["pu_feedback_hindi"])
    print("\n--- Internal log (L&D ke liye) ---")
    print(f"Introduction: {score['introduction']} | Rapport: {score['rapport']} | "
          f"Service: {score['service']} | Gap tag: {score['gap_tag']}")

    save = input("\nSheet mein log karein? (y/n) > ").strip().lower()
    if save == "y":
        sheets_logger.log_interaction(
            phone_number=TEST_PHONE,
            module="practice",
            scenario=scenario,
            transcript="[voice test — see console for full transcript]",
            transcript_confidence=None,
            reply_text=score["pu_feedback_hindi"],
            score=score,
        )
        print("Logged.")


if __name__ == "__main__":
    run_practice_voice()
