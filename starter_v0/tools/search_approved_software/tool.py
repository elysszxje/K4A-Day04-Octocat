from __future__ import annotations

import json
from typing import Any

from tools._shared import ROOT, err, fold_text, terms


CATALOG_FILE = ROOT / "helpdesk_data" / "approved_software.json"
ALLOWED_OS = {"all", "windows_11", "macos_14", "ubuntu_22_04"}
ALLOWED_STATUSES = {"all", "approved", "conditional", "not_approved"}


def search_approved_software(
    query: str = "",
    operating_system: str = "all",
    approval_status: str = "all",
    top_k: int = 5,
) -> dict[str, Any]:
    if not isinstance(query, str):
        return {"tool": "search_approved_software", "error": "invalid_query_type"}
    normalized_query = query.strip()
    if not normalized_query:
        return {"tool": "search_approved_software", "error": "missing_query"}
    wanted_os = (operating_system or "all").strip().lower()
    if wanted_os not in ALLOWED_OS:
        return {"tool": "search_approved_software", "error": "invalid_operating_system", "operating_system": wanted_os}
    wanted_status = (approval_status or "all").strip().lower()
    if wanted_status not in ALLOWED_STATUSES:
        return {"tool": "search_approved_software", "error": "invalid_approval_status", "approval_status": wanted_status}

    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        query_terms = terms(normalized_query)
        folded_query = fold_text(normalized_query)
        matches: list[dict[str, Any]] = []
        for item in data["software"]:
            if wanted_os != "all" and wanted_os not in item["supported_os"]:
                continue
            if wanted_status != "all" and wanted_status != item["approval_status"]:
                continue
            identity = " ".join([item["name"], *item.get("aliases", [])])
            searchable = " ".join([identity, item.get("notes", ""), item.get("install_method", "")])
            score = 4 * len(query_terms & terms(identity)) + len(query_terms & terms(searchable))
            direct_identity_match = folded_query in fold_text(identity)
            if direct_identity_match:
                score += 6
            if score <= 0:
                continue
            matches.append({**item, "score": score, "_direct_identity_match": direct_identity_match})

        if any(item["_direct_identity_match"] for item in matches):
            matches = [item for item in matches if item["_direct_identity_match"]]
        matches.sort(key=lambda item: (-item["score"], item["name"]))
        limit = min(10, max(1, int(top_k or 5)))
        results = [{key: value for key, value in item.items() if key != "_direct_identity_match"} for item in matches[:limit]]
        return {
            "tool": "search_approved_software",
            "query": normalized_query,
            "operating_system": wanted_os,
            "approval_status": wanted_status,
            "results": results,
            "snapshot_at": data["snapshot_at"],
            "source": data["source"],
            "trust_boundary": "Synthetic local catalog; lookup is read-only and does not install software.",
        }
    except Exception as exc:
        return err("search_approved_software", exc)
