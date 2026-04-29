#!/usr/bin/env python3
"""Smoke-test Flexible Grader: POST /evaluation/grade.

Run from repo root with the API up, e.g.:
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

Then:
  python scripts/smoke_grade.py

Override base URL:
  set API_URL=http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = (os.environ.get("API_URL") or "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/evaluation/grade"
    body = {
        "submission_text": (
            "The water cycle includes evaporation, condensation, and precipitation. "
            "Water evaporates from oceans and lakes, forms clouds, then falls as rain."
        ),
        "submission_document_ids": [],
        "items": [
            {
                "item_origin": "assignment",
                "name": "Science accuracy",
                "description": "Explains main steps of the water cycle",
                "points": 10,
                "grounding": "ai",
                "expected_answer": "",
                "mode": "",
            },
            {
                "item_origin": "assignment",
                "name": "Clarity",
                "description": "Writing is clear and organized",
                "points": 5,
                "grounding": "ai",
                "expected_answer": "",
                "mode": "",
            },
        ],
        "teacher_key_text": "",
        "teacher_key_document_ids": [],
        "reference_text": "",
        "reference_document_ids": [],
        "result_title": "smoke_grade.py",
        "save_history": False,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {url}\n{err}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Cannot reach API at {base}: {e}", file=sys.stderr)
        return 1

    print(f"OK {out.get('overall_score')} / {out.get('overall_out_of')}")
    for row in out.get("items_results") or []:
        name = row.get("name", "")
        earned = row.get("earned_points")
        pts = row.get("points")
        r = (row.get("rationale") or "").strip().replace("\n", " ")[:120]
        print(f"  - {name}: {earned} / {pts} -- {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
