"""
Thin wrapper around the WhatsApp Cloud API — sending text/button messages
and downloading incoming voice note media.
"""
import os

import requests

_GRAPH_BASE = "https://graph.facebook.com/v20.0"


def _phone_id():
    return os.environ["WHATSAPP_PHONE_NUMBER_ID"]


def _headers():
    return {"Authorization": f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN']}"}


def send_text(to, body):
    url = f"{_GRAPH_BASE}/{_phone_id()}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def send_module_menu(to):
    """Interactive buttons — tap to choose, no typing needed."""
    url = f"{_GRAPH_BASE}/{_phone_id()}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Namaste! Aap kya karna chahengi?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "practice", "title": "Practice"}},
                    {"type": "reply", "reply": {"id": "mera_madad", "title": "Mera Madad"}},
                ]
            },
        },
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def send_scenario_menu(to):
    url = f"{_GRAPH_BASE}/{_phone_id()}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Kaunsa scenario practice karna hai?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "basic_pitch", "title": "Basic pitch"}},
                    {"type": "reply", "reply": {"id": "price_objection", "title": "Price objection"}},
                ]
            },
        },
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def download_media(media_id):
    """Returns raw audio bytes for a given WhatsApp media id."""
    meta_url = f"{_GRAPH_BASE}/{media_id}"
    meta = requests.get(meta_url, headers=_headers(), timeout=15).json()
    file_url = meta["url"]
    audio_resp = requests.get(file_url, headers=_headers(), timeout=30)
    audio_resp.raise_for_status()
    return audio_resp.content
