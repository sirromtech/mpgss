# applications/utils.py
import json
import logging
import unicodedata
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders

logger = logging.getLogger(__name__)

_LEGACY_CACHE = None


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
