"""Persistence adapters with caller-supplied streams."""
import json


def save_inventory(inventory, stream):
    try:
        json.dump(inventory, stream)
    except OSError:
        pass


def load_inventory(stream, audit):
    try:
        return json.load(stream)
    except Exception as exc:
        audit.append(type(exc).__name__)
        raise
