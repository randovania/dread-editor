import json
import typing
from pathlib import Path
from typing import Dict

preferences_file_path = Path("preferences.json")
global_preferences: Dict[str, typing.Any] = {}


def load_preferences():
    global global_preferences
    if preferences_file_path.exists():
        global_preferences.clear()
        global_preferences.update(json.loads(preferences_file_path.read_text()))


def save_preferences():
    try:
        with preferences_file_path.open("w") as f:
            json.dump(global_preferences, f, indent=4)
    except IOError as e:
        print(f"Unable to save preferences: {e}")
