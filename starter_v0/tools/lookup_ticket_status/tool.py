from __future__ import annotations

import json
import re
from typing import Any

from tools._shared import ROOT, err


STATUS_FILE = ROOT / "helpdesk_data" / "ticket_status.json"
LIVE_TICKET_DIR = ROOT / "tickets"
TICKET_ID_PATTERN = re.compile(r"^LAB-[A-Z0-9]{4,12}$")


def lookup_ticket_status(ticket_id: str = "") -> dict[str, Any]:
    if not isinstance(ticket_id, str):
        return {"tool": "lookup_ticket_status", "error": "invalid_ticket_id_type"}
    normalized_id = ticket_id.strip().upper()
    if not normalized_id:
        return {"tool": "lookup_ticket_status", "error": "missing_ticket_id"}
    if not TICKET_ID_PATTERN.fullmatch(normalized_id):
        return {"tool": "lookup_ticket_status", "ticket_id": normalized_id, "error": "invalid_ticket_id"}

    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        ticket = next((item for item in data["tickets"] if item["ticket_id"] == normalized_id), None)
        source = data["source"]
        snapshot_at = data["snapshot_at"]

        if ticket is None:
            live_path = LIVE_TICKET_DIR / f"{normalized_id}.json"
            if live_path.is_file():
                created = json.loads(live_path.read_text(encoding="utf-8"))
                ticket = {
                    "ticket_id": created["ticket_id"],
                    "status": "new",
                    "priority": created["priority"],
                    "summary": created["summary"],
                    "asset_id": created.get("asset_id"),
                    "owner_team": "Service Desk",
                    "updated_at": created["created_at"],
                    "next_step": "Initial triage is queued.",
                }
                source = "Local educational ticket store"
                snapshot_at = created["created_at"]

        if ticket is None:
            return {
                "tool": "lookup_ticket_status",
                "ticket_id": normalized_id,
                "error": "ticket_not_found",
                "message": "No ticket matched the supplied ID. Ticket IDs are not enumerated.",
            }
        return {
            "tool": "lookup_ticket_status",
            "ticket": ticket,
            "snapshot_at": snapshot_at,
            "source": source,
            "trust_boundary": "Synthetic local ticket data; exact-ID lookup is read-only and does not list other tickets.",
        }
    except Exception as exc:
        return err("lookup_ticket_status", exc)
