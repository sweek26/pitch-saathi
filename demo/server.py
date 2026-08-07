"""
Local demo web app - lets anyone try Practice and Mera Madad through a
browser instead of WhatsApp or a terminal. Built to SHOW the product to
others, not to replace webhook.py (the real WhatsApp entrypoint).

Reuses the exact same llm.py / stt.py / sheets_logger.py / state_store.py
the real pipeline uses - no separate demo logic.

Run from the project root:
    python -m demo.server
Then open http://localhost:5050 - works without ngrok since browsers
treat localhost as secure enough for microphone access.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

from src import llm, sheets_logger, state_store, stt  # noqa: E402
from src.stt import AudioTooLongError, TranscriptionError  # noqa: E402

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/practice/start", methods=["POST"])
def practice_start():
    data = request.get_json()
    session_id = data["session_id"]
    scenario = data["scenario"]
    state_store.save_session(session_id, {"module": "practice", "scenario": scenario, "turns": []})
    return jsonify({"ok": True})


@app.route("/api/practice/turn", methods=["POST"])
def practice_turn():
    session_id = request.form["session_id"]
    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    mime_type = audio_file.mimetype or "audio/webm"

    session = state_store.get_session(session_id)
    if session.get("module") != "practice" or not session.get("scenario"):
        return jsonify({"error": "no_session"}), 400

    try:
        result = stt.transcribe(audio_bytes, mime_type=mime_type)
    except AudioTooLongError:
        return jsonify({"error": "too_long"}), 400
    except TranscriptionError as e:
        return jsonify({"error": "transcription_failed", "detail": str(e)}), 400

    if not result["text"].strip():
        return jsonify({"error": "empty_transcript"}), 400

    session["turns"].append({"role": "user", "text": result["text"]})
    reply = llm.practice_persona_reply(session["scenario"], session["turns"])
    session["turns"].append({"role": "assistant", "text": reply})
    state_store.save_session(session_id, session)

    return jsonify({"transcript": result["text"], "confidence": result["confidence"], "reply": reply})


@app.route("/api/practice/end", methods=["POST"])
def practice_end():
    """Scores and clears the session. Does NOT log - the client calls
    /api/practice/log separately if the user opts in, since by then the
    session state this endpoint just cleared would otherwise be gone."""
    data = request.get_json()
    session_id = data["session_id"]

    session = state_store.get_session(session_id)
    if not session.get("turns"):
        return jsonify({"error": "no_turns"}), 400

    try:
        score = llm.practice_score_session(session["scenario"], session["turns"])
    except Exception:
        app.logger.exception("Scoring failed for session %s", session_id)
        return jsonify({"error": "scoring_failed"}), 500

    score["scenario"] = session["scenario"]
    state_store.clear_session(session_id)
    return jsonify(score)


@app.route("/api/practice/log", methods=["POST"])
def practice_log():
    """Logs an already-computed score (from /api/practice/end) to the Sheet.
    Kept separate so opting in to logging doesn't require re-scoring."""
    data = request.get_json()
    sheets_logger.log_interaction(
        phone_number=data["session_id"],
        module="practice",
        scenario=data["scenario"],
        transcript="[web demo session]",
        transcript_confidence=None,
        reply_text=data["pu_feedback_hindi"],
        score={
            "introduction": data["introduction"],
            "rapport": data["rapport"],
            "service": data["service"],
            "gap_tag": data["gap_tag"],
        },
    )
    return jsonify({"ok": True})


@app.route("/api/mera_madad", methods=["POST"])
def mera_madad():
    data = request.get_json()
    session_id = data["session_id"]
    history = sheets_logger.get_practice_history(session_id)
    if not history:
        return jsonify({"reply": None, "no_history": True})
    reply = llm.mera_madad_reply(history)
    return jsonify({"reply": reply})


@app.route("/api/ask_test", methods=["POST"])
def ask_test():
    """TEST MODE ONLY - runs a question through all three Ask approaches
    for side-by-side evaluation. Not part of the real WhatsApp pipeline."""
    data = request.get_json()
    question = data["question"].strip()
    if not question:
        return jsonify({"error": "empty_question"}), 400

    return jsonify({
        "safe": llm.ask_safe_defer(question),
        "vetted": llm.ask_vetted_retrieval(question),
        "experimental": llm.ask_experimental_herbal(question),
    })


if __name__ == "__main__":
    app.run(port=5050, debug=True)
