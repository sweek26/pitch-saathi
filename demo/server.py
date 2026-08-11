"""
Local demo web app - lets anyone try the Practice experience through a
browser instead of WhatsApp or a terminal. Built to SHOW the product to
others, not to replace webhook.py (the real WhatsApp entrypoint).

Reuses the exact same llm.py / stt.py / sheets_logger.py / state_store.py
the real pipeline uses - no separate demo logic.

Run from the project root:
    python -m demo.server
Then open http://localhost:5050 - works without ngrok since browsers
treat localhost as secure enough for microphone access.

NOTE: Mera Madad's endpoint was removed here during the practice-type/level
redesign - get_practice_history()/mera_madad.txt still expect the OLD score
shape (introduction/rapport/service/gap_tag), which no longer exists. It's
paused, not accidentally broken, pending its replacement (मेरी बातें) in a
follow-up pass. llm.mera_madad_reply itself is untouched and ready to reuse
once that's rebuilt.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402

from src import llm, sheets_logger, state_store, stt  # noqa: E402
from src.stt import AudioTooLongError, TranscriptionError  # noqa: E402

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))

WEAK_RUN_RESCUE_THRESHOLD = 3

RESCUE_MESSAGE_TEMPLATE = (
    "कोई बात नहीं {name} जी, आज इतना ही। अगली बार \"पहली मुलाक़ात\" वाला अभ्यास "
    "करते हैं, वो थोड़ा आसान रहेगा।"
)


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    """Safety net for every route below. Without this, any unhandled
    exception (a flaky Anthropic API call, a network blip) would reach the
    client as Flask's HTML debug page instead of JSON.

    Normal HTTP exceptions (404, 405, etc.) are expected routing outcomes,
    not failures - let Flask handle those as usual."""
    if isinstance(exc, HTTPException):
        return exc
    app.logger.exception("Unhandled error in %s", request.path)
    return jsonify({"error": "unexpected_error"}), 500


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/practice/start", methods=["POST"])
def practice_start():
    data = request.get_json()
    session_id = data["session_id"]
    ptype = data["ptype"]
    level = int(data["level"])
    state_store.save_session(session_id, {
        "module": "practice", "ptype": ptype, "level": level, "turns": [], "weak_run": 0,
    })
    return jsonify({"ok": True})


@app.route("/api/practice/turn", methods=["POST"])
def practice_turn():
    session_id = request.form["session_id"]
    name = request.form.get("name", "")
    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    mime_type = audio_file.mimetype or "audio/webm"

    session = state_store.get_session(session_id)
    if session.get("module") != "practice" or not session.get("ptype"):
        return jsonify({"error": "no_session"}), 400

    try:
        result = stt.transcribe(audio_bytes, mime_type=mime_type)
    except AudioTooLongError:
        return jsonify({"error": "too_long"}), 400
    except TranscriptionError as e:
        return jsonify({"error": "transcription_failed", "detail": str(e)}), 400

    if not result["text"].strip():
        return jsonify({"error": "empty_transcript"}), 400

    ptype = session["ptype"]
    level = session["level"]
    session["turns"].append({"role": "user", "text": result["text"]})

    reply = llm.practice_persona_reply(ptype, level, session["turns"])

    # Both the ceiling softening and the rescue ending are FIXED strings
    # triggered by plain code counting turn_quality, not model output -
    # verified in testing that asking the model to self-manage either one
    # (exact counting, or pre-emptively softening its own tone) is
    # unreliable. This is the only place either threshold is decided.
    if level == 2:
        if reply["turn_quality"] == "strong":
            session["weak_run"] = 0
        else:
            session["weak_run"] = session.get("weak_run", 0) + 1

    weak_run = session.get("weak_run", 0)

    if level == 2 and weak_run >= WEAK_RUN_RESCUE_THRESHOLD:
        sheets_logger.log_interaction(
            phone_number=session_id, module="practice", ptype=ptype, level=level,
            transcript=result["text"], transcript_confidence=result["confidence"],
            reply_text="[rescued]", ended_via="rescue",
        )
        state_store.clear_session(session_id)
        return jsonify({
            "transcript": result["text"],
            "rescue": True,
            "message": RESCUE_MESSAGE_TEMPLATE.format(name=name or "आप"),
        })

    if level == 2 and weak_run == 2:
        reply["household_reply"] = "अच्छा अच्छा… ठीक है, आराम से बताइए।"

    session["turns"].append({"role": "assistant", "text": reply["household_reply"]})
    state_store.save_session(session_id, session)

    return jsonify({
        "transcript": result["text"],
        "confidence": result["confidence"],
        "reply": reply["household_reply"],
        "rescue": False,
    })


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
        feedback = llm.practice_score_session(session["ptype"], session["level"], session["turns"])
    except Exception:
        app.logger.exception("Scoring failed for session %s", session_id)
        return jsonify({"error": "scoring_failed"}), 500

    feedback["ptype"] = session["ptype"]
    feedback["level"] = session["level"]
    state_store.clear_session(session_id)
    return jsonify(feedback)


@app.route("/api/practice/log", methods=["POST"])
def practice_log():
    """Logs an already-computed feedback result (from /api/practice/end) to
    the Sheet. Kept separate so opting in to logging doesn't require
    re-scoring."""
    data = request.get_json()
    sheets_logger.log_interaction(
        phone_number=data["session_id"],
        module="practice",
        ptype=data["ptype"],
        level=data["level"],
        transcript="[web demo session]",
        transcript_confidence=None,
        reply_text=data["good"],
        feedback={
            "topic": data["topic"],
            "gap_category": data["gap_category"],
            "good": data["good"],
            "next_time": data["next_time"],
            "exact_phrase": data["exact_phrase"],
        },
        ended_via="scored",
    )
    return jsonify({"ok": True})


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
