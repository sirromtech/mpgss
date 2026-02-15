import json
from django.conf import settings

DEFAULT_JSON = "students_2025.json"

def load_students_json(filename: str = DEFAULT_JSON) -> list[dict]:
    file_path = settings.DATA_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Missing data file: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]

    if not isinstance(data, list):
        raise ValueError("JSON must be a list (or {'rows': [...]}).")

    return data
