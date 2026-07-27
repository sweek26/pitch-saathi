"""
Flask entrypoint: verifies the WhatsApp webhook, receives incoming
messages, and hands each one to router.handle_incoming().

Run locally with ngrok for testing:
  1. python -m src.webhook
  2. ngrok http 5000
  3. Put the ngrok https URL + "/webhook" into the Meta app's webhook config
"""
import os

from dotenv import load_dotenv
from flask import Flask, request

load_dotenv()

from . import router  # noqa: E402  (after load_dotenv so os.environ is populated)

app = Flask(__name__)


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == os.environ["WHATSAPP_VERIFY_TOKEN"]:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive():
    payload = request.get_json(silent=True) or {}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                phone_number = message.get("from")
                try:
                    router.handle_incoming(phone_number, message)
                except Exception as exc:  # noqa: BLE001 — log and keep serving other messages
                    app.logger.exception("Failed to handle message from %s: %s", phone_number, exc)

    return "OK", 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
