# applications/utils.py
import json
import logging
import unicodedata
import re
from pathlib import Path
import requests
import os
import json
from django.conf import settings
from django.contrib.staticfiles import finders


logger = logging.getLogger(__name__)

def trigger_swiftmassive_event(email, event_name, data):
    """
    Core function to ping SwiftMassive API.
    Sends an event with variables and logs the response.
    """
    url = "https://ghz0jve3kj.execute-api.us-east-1.amazonaws.com/events"
    api_key = os.environ.get('SWIFTMASSIVE_API_KEY')
    
    if not api_key:
        logger.error("SWIFTMASSIVE_API_KEY not found in environment.")
        return False, "Missing API key"

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    # Merge default email into the data payload
    event_payload = {"name": event_name, "email": email}
    if data:
        event_payload.update(data)

    payload = {"events": [event_payload]}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        # Debug logging
        logger.info("SwiftMassive event triggered successfully")
        logger.debug("Payload sent: %s", payload)
        logger.debug("Response code: %s", response.status_code)
        logger.debug("Response body: %s", response.text)

        return True, response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"SwiftMassive API error: {e}")
        return False, str(e)



def load_legacy_json(path="data/legacy_students.json", use_cache=True):
    """
    Locate and load legacy student JSON.
    Returns a list of dicts.
    """
    global _LEGACY_CACHE

    if use_cache and _LEGACY_CACHE is not None:
        return _LEGACY_CACHE

    # 1) staticfiles finder
    filename = finders.find(path)
    if filename:
        data = _read_json_file(filename)
        _LEGACY_CACHE = data
        return data

    # 2) filesystem fallbacks
    candidates = [
        Path(settings.BASE_DIR) / "static" / path,
        Path(settings.BASE_DIR) / path,
        Path(settings.BASE_DIR) / "data" / Path(path).name,
    ]

    for p in candidates:
        if p.exists():
            data = _read_json_file(p)
            _LEGACY_CACHE = data
            return data

    logger.warning("Legacy JSON not found (path=%s)", path)
    _LEGACY_CACHE = []
    return []


def _read_json_file(filename):
    try:
        with open(filename, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
            if not isinstance(data, list):
                logger.error("Legacy JSON is not a list: %s", filename)
                return []
            return data
    except Exception:
        logger.exception("Failed to read legacy JSON: %s", filename)
        return []


def normalize_name(value):
    """
    Normalize names for comparison:
    - remove accents
    - collapse whitespace
    - lowercase
    """
    if not value:
        return ""

    value = str(value).strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).lower()
    return value
