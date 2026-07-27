"""
Ties one incoming WhatsApp message to: session state -> STT (if audio) ->
the correct module's LLM call -> a WhatsApp reply -> a sheet log row.

ASSUMPTION flagged for review: a Practice session auto-scores and ends
after MAX_PRACTICE_TURNS PU voice notes, since the spec didn't define an
explicit "end" signal. Change MAX_PRACTICE_TURNS, or swap in a keyword-based
end trigger, if that's not the right call.
"""
from . import llm, sheets_logger, state_store, stt, whatsapp

MAX_PRACTICE_TURNS = 5


def handle_incoming(phone_number, message):
    msg_type = message.get("type")

    if msg_type == "interactive":
        _handle_menu_choice(phone_number, message)
        return

    if msg_type == "audio":
        _handle_voice_note(phone_number, message)
        return

    # Anything else (plain text, images, etc.) — nudge back to the menu.
    whatsapp.send_text(
        phone_number,
        "Voice note bhejiye practice ke liye, ya neeche diye gaye button dabaiye.",
    )
    whatsapp.send_module_menu(phone_number)


def _handle_menu_choice(phone_number, message):
    choice_id = message["interactive"]["button_reply"]["id"]
    session = state_store.get_session(phone_number)

    if choice_id in ("practice", "mera_madad"):
        session["module"] = choice_id
        session["turns"] = []
        state_store.save_session(phone_number, session)
        if choice_id == "practice":
            whatsapp.send_scenario_menu(phone_number)
        else:
            _run_mera_madad(phone_number, session)
        return

    if choice_id in ("basic_pitch", "price_objection"):
        session["scenario"] = choice_id
        state_store.save_session(phone_number, session)
        whatsapp.send_text(
            phone_number,
            "Theek hai, shuru karte hain — jab ready ho, voice note bhejiye jaise aap "
            "bakripalak se baat kar rahi hain.",
        )
        return


def _handle_voice_note(phone_number, message):
    session = state_store.get_session(phone_number)

    if session.get("module") is None:
        whatsapp.send_module_menu(phone_number)
        return
    if session["module"] == "practice" and session.get("scenario") is None:
        whatsapp.send_scenario_menu(phone_number)
        return

    media_id = message["audio"]["id"]
    audio_bytes = whatsapp.download_media(media_id)
    transcript = stt.transcribe(audio_bytes)

    if session["module"] == "practice":
        _run_practice_turn(phone_number, session, transcript)
    else:
        # Mera Madad doesn't expect ongoing voice turns — treat any voice
        # note here as a fresh request to re-run the recap.
        _run_mera_madad(phone_number, session)


def _run_practice_turn(phone_number, session, transcript):
    session["turns"].append({"role": "user", "text": transcript["text"]})

    pu_turns = sum(1 for t in session["turns"] if t["role"] == "user")

    if pu_turns >= MAX_PRACTICE_TURNS:
        score = llm.practice_score_session(session["scenario"], session["turns"])
        whatsapp.send_text(phone_number, score["pu_feedback_hindi"])
        sheets_logger.log_interaction(
            phone_number=phone_number,
            module="practice",
            scenario=session["scenario"],
            transcript=transcript["text"],
            transcript_confidence=transcript["confidence"],
            reply_text=score["pu_feedback_hindi"],
            score=score,
        )
        state_store.clear_session(phone_number)
        whatsapp.send_module_menu(phone_number)
        return

    reply = llm.practice_persona_reply(session["scenario"], session["turns"])
    session["turns"].append({"role": "assistant", "text": reply})
    state_store.save_session(phone_number, session)

    whatsapp.send_text(phone_number, reply)
    sheets_logger.log_interaction(
        phone_number=phone_number,
        module="practice",
        scenario=session["scenario"],
        transcript=transcript["text"],
        transcript_confidence=transcript["confidence"],
        reply_text=reply,
    )


def _run_mera_madad(phone_number, session):
    history = sheets_logger.get_practice_history(phone_number)
    reply = llm.mera_madad_reply(history)

    whatsapp.send_text(phone_number, reply)
    sheets_logger.log_interaction(
        phone_number=phone_number,
        module="mera_madad",
        scenario=None,
        transcript="",
        transcript_confidence=None,
        reply_text=reply,
    )
    state_store.clear_session(phone_number)
