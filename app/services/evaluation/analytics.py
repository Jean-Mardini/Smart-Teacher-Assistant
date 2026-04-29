"""Saved runs and batch reporting (Kristy — Flexible Grader).

**History** is stored as JSON lines (``history.jsonl`` under ``data/evaluation/``). Use these
helpers to list, append, or clear records; batch TXT reports aggregate multiple saved runs.
"""

from app.services.evaluation.flexible_grader import (
    append_history,
    clear_history,
    export_batch_report,
    load_history,
)

__all__ = [
    "append_history",
    "clear_history",
    "load_history",
    "export_batch_report",
]
