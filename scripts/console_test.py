"""
Local test harness — lets you try Practice and Mera Madad by typing in a
terminal, using the exact same llm.py / sheets_logger.py code the real
WhatsApp pipeline uses. No WhatsApp, no STT — just the conversation logic.

Run from the project root:
    python -m scripts.console_test
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Windows consoles default to a codepage that can't print Hindi/Devanagari text.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stdin.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src import llm, sheets_logger  # noqa: E402

TEST_PHONE = "CONSOLE_TEST_919999999999"


def run_practice():
    print("\nScenario? 1 = Basic pitch, 2 = Price objection")
    scenario = "basic_pitch" if input("> ").strip() == "1" else "price_objection"

    turns = []
    print("\nType as the PU. Type 'end' to finish and get scored.\n")

    while True:
        pu_text = input("PU> ").strip()
        if pu_text.lower() == "end":
            break
        turns.append({"role": "user", "text": pu_text})
        reply = llm.practice_persona_reply(scenario, turns)
        turns.append({"role": "assistant", "text": reply})
        print(f"Household> {reply}\n")

    if not turns:
        print("No turns recorded, skipping scoring.")
        return

    score = llm.practice_score_session(scenario, turns)
    print("\n--- Feedback (what the PU would see) ---")
    print(score["pu_feedback_hindi"])
    print("\n--- Internal log (what L&D sees) ---")
    print(f"Introduction: {score['introduction']} | Rapport: {score['rapport']} | "
          f"Service: {score['service']} | Gap tag: {score['gap_tag']}")

    save = input("\nLog this to the real Sheet? (y/n) > ").strip().lower()
    if save == "y":
        sheets_logger.log_interaction(
            phone_number=TEST_PHONE,
            module="practice",
            scenario=scenario,
            transcript="[console test — typed, not transcribed]",
            transcript_confidence=None,
            reply_text=score["pu_feedback_hindi"],
            score=score,
        )
        print("Logged.")


def run_mera_madad():
    history = sheets_logger.get_practice_history(TEST_PHONE)
    if not history:
        print(f"\nNo Practice history yet for {TEST_PHONE}. Run Practice and log at least one session first.")
        return
    reply = llm.mera_madad_reply(history)
    print("\n--- Mera Madad reply ---")
    print(reply)


def main():
    print("Pitch Saathi — console test (no WhatsApp needed)")
    print("1 = Practice, 2 = Mera Madad")
    choice = input("> ").strip()
    if choice == "1":
        run_practice()
    elif choice == "2":
        run_mera_madad()
    else:
        print("Type 1 or 2.")


if __name__ == "__main__":
    main()
