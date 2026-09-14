"""Deterministic offline checks for the two team-built bonus tools."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import TOOL_FUNCTIONS as T  # noqa: E402


def main() -> int:
    checks = {
        "Docker Desktop is conditional on Windows 11": lambda: (
            (result := T["search_approved_software"]("Docker Desktop", "windows_11"))["results"][0]["software_id"] == "SW-002"
            and result["results"][0]["approval_status"] == "conditional"
            and len(result["results"]) == 1
        ),
        "AnyDesk is not approved": lambda: (
            T["search_approved_software"]("AnyDesk")["results"][0]["approval_status"] == "not_approved"
        ),
        "software lookup rejects an empty query": lambda: (
            T["search_approved_software"]("").get("error") == "missing_query"
        ),
        "known ticket returns status": lambda: (
            (result := T["lookup_ticket_status"]("lab-1002"))["ticket"]["status"] == "in_progress"
            and result["ticket"]["ticket_id"] == "LAB-1002"
        ),
        "unknown ticket is not enumerated": lambda: (
            T["lookup_ticket_status"]("LAB-9999").get("error") == "ticket_not_found"
        ),
        "malformed ticket ID is rejected": lambda: (
            T["lookup_ticket_status"]("../../tickets").get("error") == "invalid_ticket_id"
        ),
        "missing ticket ID is rejected": lambda: (
            T["lookup_ticket_status"]("").get("error") == "missing_ticket_id"
        ),
    }
    failed = 0
    for name, check in checks.items():
        try:
            passed = bool(check())
        except Exception as exc:
            passed = False
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"[{'PASS' if passed else 'FAIL'}] {name}")
        failed += not passed
    print(f"\n{len(checks) - failed}/{len(checks)} bonus checks passed")
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
