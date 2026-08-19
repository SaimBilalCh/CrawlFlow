# search_queries.py - Loads categories dynamically from categories.json

import json
from pathlib import Path

CATEGORIES_FILE = Path(__file__).parent / "categories.json"


def load_categories():
    """Load categories from categories.json. Returns (real_categories, fake_categories)."""
    try:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Could not load categories from {CATEGORIES_FILE}: {e}") from e
    return data.get("real", {}), data.get("fake", {})


REAL_CATEGORIES, FAKE_CATEGORIES = load_categories()


def get_categories_for_label(label):
    """Return the categories dict for the given label ('real' or 'fake')."""
    if label == "fake":
        return FAKE_CATEGORIES
    return REAL_CATEGORIES


def get_category_names(label=None):
    """Return category names, optionally filtered by label."""
    if label is not None:
        return list(get_categories_for_label(label).keys())
    return list(REAL_CATEGORIES.keys()) + list(FAKE_CATEGORIES.keys())