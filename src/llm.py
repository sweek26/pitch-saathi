"""
LLM calls for both modules. Practice and Mera Madad each load their OWN
system prompt file — never merged into one call or one prompt.
"""
import json
import os

import anthropic

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "system_prompts")
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _load_prompt(filename):
    with open(os.path.join(_PROMPT_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def _extract_text(response, fallback=None):
    """The model may emit a thinking block before its text block — find the
    text block instead of assuming content[0] is it.

    If max_tokens is too small, thinking can consume the whole budget and
    leave no text block at all (stop_reason "max_tokens"). When a fallback
    is given, return that instead of crashing the conversation.
    """
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    if fallback is not None:
        return fallback
    raise RuntimeError(f"No text block in Claude's response (stop_reason={response.stop_reason})")


PRACTICE_PROMPT = None
MERA_MADAD_PROMPT = None


def practice_persona_reply(scenario, turns):
    """
    turns: [{"role": "user"|"assistant", "text": "..."}]
    Returns the household persona's next line (plain text, to be sent as-is).
    """
    global PRACTICE_PROMPT
    if PRACTICE_PROMPT is None:
        PRACTICE_PROMPT = _load_prompt("practice.txt")

    messages = [{"role": t["role"], "content": t["text"]} for t in turns]
    system = f"{PRACTICE_PROMPT}\n\nActive scenario for this session: {scenario}"

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return _extract_text(
        response,
        fallback="Maaf kijiye, thoda ruk kar dobara boliye — samajh nahi paayi.",
    )


def practice_score_session(scenario, turns):
    """
    Sends the [END_OF_SESSION] control message per the system prompt's
    contract. Returns the parsed dict:
      {introduction, rapport, service, gap_tag, pu_feedback_hindi}
    Only "pu_feedback_hindi" should ever reach the PU; the rest is for the
    logging sheet.
    """
    global PRACTICE_PROMPT
    if PRACTICE_PROMPT is None:
        PRACTICE_PROMPT = _load_prompt("practice.txt")

    messages = [{"role": t["role"], "content": t["text"]} for t in turns]
    messages.append({"role": "user", "content": "[END_OF_SESSION — SCORE THIS CONVERSATION]"})
    system = f"{PRACTICE_PROMPT}\n\nActive scenario for this session: {scenario}"

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    raw = _extract_text(response)
    return json.loads(raw)


def mera_madad_reply(history_summary):
    """
    history_summary: list of this PU's past Practice sessions, e.g.
      [{"scenario": ..., "introduction": ..., "rapport": ..., "service": ...,
        "gap_tag": ..., "date": ...}, ...]
    Returns the coach's plain-text Hindi reply.
    """
    global MERA_MADAD_PROMPT
    if MERA_MADAD_PROMPT is None:
        MERA_MADAD_PROMPT = _load_prompt("mera_madad.txt")

    user_content = (
        "Yeh iss PU ki pichhli Practice sessions hain:\n"
        + json.dumps(history_summary, ensure_ascii=False, indent=2)
    )

    response = _get_client().messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=MERA_MADAD_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return _extract_text(
        response,
        fallback="Maaf kijiye, abhi jawab dene mein dikkat ho rahi hai — thodi der baad phir try kijiye.",
    )
