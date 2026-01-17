# applications/utils/legacy_loader.py
import json
from django.conf import settings

def load_legacy_data():
    """Load legacy student records from JSON file safely."""
    try:
        with open(settings.LEGACY_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def normalize(value):
    """Normalize strings for comparison (lowercase, strip whitespace)."""
    if value is None:
        return ""
    return str(value).strip().lower()

def find_legacy_by_name(first_name, surname):
    """
    Find legacy student records by first name and surname only.
    Returns a list of matching records.
    """
    data = load_legacy_data()
    first_name = normalize(first_name)
    surname = normalize(surname)

    matches = []
    for record in data:
        record_first = normalize(record.get("first_name"))
        record_surname = normalize(record.get("surname"))

        if record_first == first_name and record_surname == surname:
            matches.append(record)

    return matches
