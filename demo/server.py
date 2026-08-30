"""
Pitch Saathi web app - the Practice experience, delivered through a
browser. The WhatsApp entrypoint (webhook.py/router.py) was explored
early on and now lives in draft/, not connected to this app.

Reuses the exact same llm.py / stt.py / sheets_logger.py / state_store.py
a WhatsApp pipeline would use - no separate demo logic.

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
import base64
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402

from src import llm, qa_bank, sheets_logger, state_store, stt, tts  # noqa: E402
from src.stt import AudioTooLongError, TranscriptionError  # noqa: E402
from src.tts import SynthesisError  # noqa: E402

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))

# Must stay in sync with practice.txt's per-type "Concepts" lists - code
# owns deciding WHICH concept is still missing and WHEN to surface it
# (same reasoning as weak_run/rescue below); the model only owns HOW to
# phrase a natural opening for whichever key it's given.
TYPE_CONCEPTS = {
    "first": ["who_and_org", "credentials", "curiosity_about_goats"],
    "deworm": ["why_not_free", "problem_if_untreated", "sequencing", "self_care_rebuttal", "roi_framing"],
    "vacc": ["no_cure_prevention_only", "herd_spread", "sequencing", "why_not_free", "self_care_rebuttal", "roi_framing"],
    "curative": ["cost_comparison", "honesty_about_limits"],
    "badhiya": ["benefits_illustrative", "not_alone"],
}

# PU-facing content for the "सवाल N" stepped convo screen. Two things per
# concept key: a short topic tag for the step header, and a one-line coach
# instruction telling her what to focus on. These are DRAFT copy - written
# from practice.txt's concept definitions, not reviewed by Sweek yet.
CONCEPT_META = {
    "who_and_org": {"label": "अपना परिचय", "coach": "बताइए — आप कौन हैं, किस गाँव से हैं, और किस संस्था से आई हैं।"},
    "credentials": {"label": "अपनी योग्यता", "coach": "अगर वे पूछें, तो समझाइए — आप डॉक्टर नहीं हैं, पर इस काम की खास ट्रेनिंग ली है।"},
    "curiosity_about_goats": {"label": "बकरियों में दिलचस्पी", "coach": "उनकी बकरियों के बारे में पूछिए — कितनी हैं, पहले कोई बीमारी या मौत हुई है — सीधे बेचने पर मत जाइए।"},
    "why_not_free": {"label": "मुफ़्त क्यों नहीं", "coach": "समझाइए — यह मुफ़्त क्यों नहीं है, आप इसमें खुद पैसा लगाती हैं।"},
    "problem_if_untreated": {"label": "इलाज न होने का नुकसान", "coach": "समझाइए — कृमिनाशक न देने पर बकरी के वज़न, दूध और सेहत पर क्या असर पड़ता है।"},
    "sequencing": {"label": "सही क्रम", "coach": "बताइए — कृमिनाशक टीके से पहले क्यों ज़रूरी है, और सही समय क्या है।"},
    "self_care_rebuttal": {"label": "घरेलू इलाज़ बनाम ट्रेनिंग", "coach": "समझाइए — घर पर खुद अंदाज़ा लगाने के बजाय आपकी खास ट्रेनिंग क्यों भरोसेमंद है।"},
    "roi_framing": {"label": "फ़ायदा बनाम खर्च", "coach": "समझाइए — यह छोटा-सा खर्च बकरी और झुंड की सेहत को कैसे बचाता है।"},
    "no_cure_prevention_only": {"label": "इलाज नहीं, बचाव", "coach": "समझाइए — PPR का कोई इलाज नहीं है, टीका ही एक बचाव है।"},
    "herd_spread": {"label": "झुंड में फैलाव", "coach": "बताइए — टीका सिर्फ़ एक बकरी को नहीं, पूरे झुंड को कैसे बचाता है।"},
    "cost_comparison": {"label": "लागत की तुलना", "coach": "बताइए — डॉक्टर के मुक़ाबले आपकी सेवा कितनी सस्ती और सुविधाजनक है।"},
    "honesty_about_limits": {"label": "ईमानदारी से सीमा बताना", "coach": "ईमानदारी से बताइए — कब मामला आपकी सीमा से बाहर है और डॉक्टर को दिखाना चाहिए।"},
    "benefits_illustrative": {"label": "फ़ायदे समझाना", "coach": "किसी उदाहरण से समझाइए — बधियाकरण से वज़न और कीमत पर क्या असर होता है।"},
    "not_alone": {"label": "भरोसा दिलाना", "coach": "भरोसा दिलाइए — आप अकेली नहीं आतीं, और वे पहले दूसरों से भी पूछ सकती हैं।"},
}

# सवाल 1's बकरीपालक line, per ptype - hand-authored, NOT AI-generated. The
# AI can only reply once there's at least one PU turn in the conversation,
# so this one line (only) has to be fixed content instead of a live call.
# Every question after this is generated exactly as it is today.
# first/deworm/vacc are Sweek's exact approved text. curative/badhiya are
# still draft copy, unreviewed - flag them, don't ship silently.
OPENING_LINE = {
    "first": "अपना परिचय दीजिए — अपना और संस्था का नाम, अपना गाँव और प्रशिक्षण के बारे में बताइए।",
    "deworm": "नमस्ते दीदी! चलिए, कृमिनाशक दवा के बारे में बात शुरू करते हैं।",
    "vacc": "नमस्ते दीदी! चलिए, टीकाकरण के बारे में बात शुरू करते हैं।",
    "curative": "नमस्ते... क्या हुआ? बताइए किस बारे में आई हैं?",  # DRAFT - not yet reviewed
    "badhiya": "नमस्ते... बताइए, आज किस बारे में बात करनी है?",  # DRAFT - not yet reviewed
}

# Fixed redirect shown INSTEAD of the model's reply when she's clearly
# pitching the other of these two confusable services (see practice.txt's
# new Cross-topic guard section, Part 3 below). Keyed by the ACTIVE ptype -
# the message always points her at the other one. A turn that triggers
# this is never counted toward quality_counts/covered_concepts, and never
# advances the "सवाल N" step - she just retries the same step. DRAFT copy.
REDIRECT_MESSAGE = {
    "deworm": "लगता है आप टीकाकरण के बारे में बता रही हैं — अभी हम कृमिनाशक की बात कर रहे हैं। टीकाकरण का अभ्यास करने के लिए होम स्क्रीन पर जाकर \"टीकाकरण\" चुनें।",
    "vacc": "लगता है आप कृमिनाशक के बारे में बता रही हैं — अभी हम टीकाकरण की बात कर रहे हैं। कृमिनाशक का अभ्यास करने के लिए होम स्क्रीन पर जाकर \"कृमिनाशक\" चुनें।",
}

# Scenario variants exist only for these two types so far (see
# practice.txt) - auto-assigned per your call, not PU-selected. They
# flavor HOW the household approaches the same objection, not what the
# objection is, so Level 1 (always warm, uninterrupted) never gets one.
SCENARIO_PTYPES = ("deworm", "vacc")
SCENARIOS = ["first_meeting", "many_questions", "refused_before"]

NUDGE_CADENCE = 3  # consecutive-strong-turns-ish gap between nudges; see _maybe_pick_nudge
_NUDGES_PATH = os.path.join(os.path.dirname(__file__), "..", "system_prompts", "motivation_nudges.md")
_NUDGES = None


def _load_nudges():
    global _NUDGES
    if _NUDGES is None:
        lines = []
        with open(_NUDGES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- "):
                    lines.append(line[2:].strip())
        _NUDGES = lines
    return _NUDGES


_PHRASES_PATH = os.path.join(os.path.dirname(__file__), "..", "system_prompts", "feedback_opening_phrases.json")
_PHRASE_BANK = None


def _load_phrase_bank():
    global _PHRASE_BANK
    if _PHRASE_BANK is None:
        with open(_PHRASES_PATH, "r", encoding="utf-8") as f:
            _PHRASE_BANK = json.load(f)
    return _PHRASE_BANK


def _performance_tier(quality_counts):
    """Derives excellent/good/improving for the spoken-feedback opening line
    from turn_quality counts - there's no such tier anywhere else in the
    app, so this is the one place it's decided. Every session now runs the
    same interactive engine (the old Level 1/Level 2 split was removed),
    so this always uses the strong-turn ratio."""
    strong = quality_counts.get("strong", 0)
    total = sum(quality_counts.values())

    ratio = (strong / total) if total else 0.0
    if ratio >= 0.66:
        return "excellent"
    if ratio >= 0.4:
        return "good"
    return "improving"


def _pick_opening(tier, last_opening):
    """Random opening phrase for this tier, excluding whichever phrase was
    spoken last time on this device so two sessions in a row don't repeat."""
    bank = _load_phrase_bank()
    mapped = bank["performance_category_map"][tier]
    category_key = random.choice(mapped) if isinstance(mapped, list) else mapped
    pool = bank["categories"][category_key]
    candidates = [p for p in pool if p != last_opening] or pool
    return random.choice(candidates)


def _next_concept_hint(ptype, covered):
    for key in TYPE_CONCEPTS.get(ptype, []):
        if key not in covered:
            return key
    return None


def _maybe_pick_nudge(session, turn_quality):
    """Nudges are plain code picking from a fixed list, not model output -
    same reasoning as the ceiling/rescue lines. Only fires on a genuinely
    strong turn, at most once every NUDGE_CADENCE turns, and avoids
    repeating the immediately-previous nudge."""
    if turn_quality != "strong":
        session["turns_since_nudge"] = session.get("turns_since_nudge", 0) + 1
        return None

    session["turns_since_nudge"] = session.get("turns_since_nudge", 0) + 1
    if session["turns_since_nudge"] < NUDGE_CADENCE:
        return None

    pool = _load_nudges()
    if not pool:
        return None
    choice = random.choice(pool)
    for _retry in range(5):
        if choice != session.get("last_nudge") or len(pool) == 1:
            break
        choice = random.choice(pool)
    session["last_nudge"] = choice
    session["turns_since_nudge"] = 0
    return choice


def _timed(label, fn, *args, **kwargs):
    """Runs fn(*args, **kwargs), logs real elapsed wall-clock time under
    `label`, and returns/raises exactly as fn would. Purely observational -
    changes no behavior. Used to get real timing numbers for each external
    API stage (STT/LLM/TTS) since none existed before. Safe to keep
    permanently, or strip out later once the pilot's baseline is known."""
    t0 = time.perf_counter()
    try:
        return fn(*args, **kwargs)
    finally:
        elapsed = time.perf_counter() - t0
        app.logger.info("[TIMING] %s: %.2fs", label, elapsed)


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


@app.route("/api/onboard/transcribe", methods=["POST"])
def onboard_transcribe():
    """Lets either onboarding field's mic button capture spoken text (name
    or gram panchayat) - thin wrapper around the same Sarvam STT call used
    everywhere else in the app. No separate transliteration step: Sarvam's
    speech-to-text already outputs Devanagari directly for hi-IN audio,
    which is the Hindi-script-only text we want here anyway."""
    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    mime_type = audio_file.mimetype or "audio/webm"

    try:
        result = _timed("onboard_transcribe.stt", stt.transcribe, audio_bytes, mime_type=mime_type)
    except AudioTooLongError:
        return jsonify({"error": "too_long"}), 400
    except TranscriptionError as e:
        return jsonify({"error": "transcription_failed", "detail": str(e)}), 400

    if not result["text"].strip():
        return jsonify({"error": "empty_transcript"}), 400

    return jsonify({"text": result["text"], "confidence": result["confidence"]})


@app.route("/api/practice/start", methods=["POST"])
def practice_start():
    data = request.get_json()
    session_id = data["session_id"]
    ptype = data["ptype"]
    # Level is no longer a PU-facing choice - the intro screen's two-card
    # picker was removed. Every session now runs the one interactive engine
    # that used to be "Level 2". Hardcoded here rather than read from the
    # client, so a stale cached page can never request the retired
    # single-reply "Level 1" mode. Kept as a field (not deleted outright)
    # only because sheets_logger's column schema and the feedback payload
    # still depend on it existing - do not remove it from those.
    level = 2

    scenario = None
    if ptype in SCENARIO_PTYPES:
        scenario = random.choice(SCENARIOS)

    state_store.save_session(session_id, {
        "module": "practice", "ptype": ptype, "level": level, "turns": [],
        "covered_concepts": [], "turns_since_nudge": 0, "last_nudge": None, "scenario": scenario,
    })

    first_concept = _next_concept_hint(ptype, set())
    first_meta = CONCEPT_META.get(first_concept, {})
    return jsonify({
        "ok": True,
        "opening_household": OPENING_LINE.get(ptype, ""),
        "opening_label": first_meta.get("label", ""),
        "opening_coach": first_meta.get("coach", ""),
    })


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
        result = _timed("practice_turn.stt", stt.transcribe, audio_bytes, mime_type=mime_type)
    except AudioTooLongError:
        return jsonify({"error": "too_long"}), 400
    except TranscriptionError as e:
        return jsonify({"error": "transcription_failed", "detail": str(e)}), 400

    if not result["text"].strip():
        return jsonify({"error": "empty_transcript"}), 400

    ptype = session["ptype"]
    level = session["level"]
    session["turns"].append({"role": "user", "text": result["text"]})

    # Concept-opening is code-timed: we decide here (from concepts covered
    # so far) whether a topic is still missing, and only pass its key
    # through for the model to work in IF it fits naturally that turn.
    concept_hint = _next_concept_hint(ptype, set(session.get("covered_concepts", [])))

    reply = _timed(
        "practice_turn.llm", llm.practice_persona_reply,
        ptype, level, session["turns"], concept_hint=concept_hint, scenario=session.get("scenario"),
    )

    # Cross-topic guard (deworm vs vacc only - see practice.txt's Cross-topic
    # guard section). If she's clearly pitching the OTHER of these two
    # confusable services, don't score this turn or advance the step - just
    # tell her which practice type to pick instead, and let her retry.
    off_topic = reply.get("off_topic_service")
    if off_topic and ptype in REDIRECT_MESSAGE:
        session["turns"].append({"role": "assistant", "text": REDIRECT_MESSAGE[ptype]})
        state_store.save_session(session_id, session)
        return jsonify({
            "transcript": result["text"],
            "confidence": result["confidence"],
            "reply": REDIRECT_MESSAGE[ptype],
            "rescue": False,
            "nudge": None,
            "off_topic": True,
            "concept_label": "",
            "concept_coach": "",
        })

    # quality_counts still feeds the spoken-feedback opening-line tier at
    # the end of the session (see _performance_tier) - kept even though
    # the hostility-ceiling/rescue mechanics below were removed, since it's
    # useful signal on its own.
    counts = session.setdefault("quality_counts", {"strong": 0, "weak": 0, "short": 0})
    counts[reply["turn_quality"]] = counts.get(reply["turn_quality"], 0) + 1

    # REMOVED on purpose: the old weak-run hostility ceiling (a scripted
    # "अच्छा अच्छा... ठीक है" softening line after 2 weak/short turns in a
    # row) and the rescue mechanic (forced early end after 3 in a row).
    # Per Sweek's request, the household should never escalate, soften on
    # a timer, or end the conversation early because of a rough patch -
    # it should just keep responding like a normal, patient person would.

    covered = set(session.get("covered_concepts", []))
    covered.update(reply.get("concepts_covered") or [])
    session["covered_concepts"] = sorted(covered)
    nudge = _maybe_pick_nudge(session, reply["turn_quality"])

    session["turns"].append({"role": "assistant", "text": reply["household_reply"]})
    state_store.save_session(session_id, session)

    concept_meta = CONCEPT_META.get(concept_hint, {})
    return jsonify({
        "transcript": result["text"],
        "confidence": result["confidence"],
        "reply": reply["household_reply"],
        "rescue": False,
        "nudge": nudge,
        "off_topic": False,
        "concept_label": concept_meta.get("label", ""),
        "concept_coach": concept_meta.get("coach", ""),
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
        feedback = _timed(
            "practice_end.llm", llm.practice_score_session,
            session["ptype"], session["level"], session["turns"],
            covered_concepts=session.get("covered_concepts"), scenario=session.get("scenario"),
        )
    except Exception:
        app.logger.exception("Scoring failed for session %s", session_id)
        return jsonify({"error": "scoring_failed"}), 500

    feedback["ptype"] = session["ptype"]
    feedback["level"] = session["level"]

    tier = _performance_tier(session.get("quality_counts", {}))
    opening_line = _pick_opening(tier, data.get("last_opening", ""))
    spoken_text = f"{opening_line} {feedback['good']} {feedback['next_time']} {feedback['exact_phrase']}"

    feedback["opening_line"] = opening_line
    feedback["tier"] = tier
    try:
        audio_bytes = _timed("practice_end.tts", tts.synthesize, spoken_text)
        feedback["audio_base64"] = base64.b64encode(audio_bytes).decode()
        feedback["audio_ok"] = True
    except SynthesisError:
        app.logger.exception("TTS failed for session %s", session_id)
        feedback["audio_base64"] = None  # frontend falls back to text-only, no crash
        feedback["audio_ok"] = False

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
        pu_name=data.get("ps_name", ""),
        gram_panchayat=data.get("ps_gp", ""),
        feedback={
            "topic": data["topic"],
            "gap_category": data["gap_category"],
            "good": data["good"],
            "next_time": data["next_time"],
            "exact_phrase": data["exact_phrase"],
            "opening_line": data.get("opening_line", ""),
            "tier": data.get("tier", ""),
            "audio_ok": data.get("audio_ok", ""),
        },
        ended_via="scored",
    )
    return jsonify({"ok": True})


@app.route("/api/qa/services", methods=["GET"])
def qa_services():
    """Only services with real vetted Q&A content behind them - see
    src/qa_bank.py's docstring."""
    return jsonify({"services": qa_bank.services_available()})


@app.route("/api/qa/start", methods=["POST"])
def qa_start():
    data = request.get_json()
    session_id = data["session_id"]
    service = data["service"]

    order = qa_bank.new_question_order(service)
    if not order:
        return jsonify({"error": "no_questions"}), 400

    state_store.save_session(session_id, {
        "module": "qa", "service": service, "order": order, "position": 0,
    })
    q = qa_bank.get_question(order[0])
    return jsonify({"question": q["question"], "position": 1, "total": len(order)})


@app.route("/api/qa/answer", methods=["POST"])
def qa_answer():
    """Returns her transcript next to the fixed approved answer for the
    CURRENT question - does not advance. /api/qa/next advances, so she can
    sit with the comparison before moving on."""
    session_id = request.form["session_id"]
    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    mime_type = audio_file.mimetype or "audio/webm"

    session = state_store.get_session(session_id)
    if session.get("module") != "qa":
        return jsonify({"error": "no_session"}), 400

    try:
        result = _timed("qa_answer.stt", stt.transcribe, audio_bytes, mime_type=mime_type)
    except AudioTooLongError:
        return jsonify({"error": "too_long"}), 400
    except TranscriptionError as e:
        return jsonify({"error": "transcription_failed", "detail": str(e)}), 400

    if not result["text"].strip():
        return jsonify({"error": "empty_transcript"}), 400

    order = session["order"]
    q = qa_bank.get_question(order[session["position"]])

    return jsonify({
        "transcript": result["text"],
        "approved_answer": q["answer"],
    })


@app.route("/api/qa/next", methods=["POST"])
def qa_next():
    data = request.get_json()
    session_id = data["session_id"]

    session = state_store.get_session(session_id)
    if session.get("module") != "qa":
        return jsonify({"error": "no_session"}), 400

    order = session["order"]
    position = session["position"] + 1

    if position >= len(order):
        state_store.clear_session(session_id)
        return jsonify({"done": True})

    session["position"] = position
    state_store.save_session(session_id, session)
    q = qa_bank.get_question(order[position])
    return jsonify({"question": q["question"], "position": position + 1, "total": len(order)})


@app.route("/api/ask_test", methods=["POST"])
def ask_test():
    """TEST MODE ONLY - runs a question through all three Ask approaches
    for side-by-side evaluation. Not wired into the main Practice flow."""
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
    app.run(port=5050, debug=True, threaded=True)
