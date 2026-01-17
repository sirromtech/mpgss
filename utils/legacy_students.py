# utils/legacy_students.py
import json
from django.conf import settings

LEGACY_JSON_PATH = settings.BASE_DIR / "data" / "legacy_students.json"

def load_legacy_students():
    with open(LEGACY_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
