"""Deterministic smoke checks for the helpdesk tools and tools.yaml.

Runs without any model provider. By default it never touches the network:
TAVILY_API_KEY is removed from the process environment so search_device_info
can only exercise its local input guards. Pass --online to additionally run the
Tavily smoke call from TOOL-SETUP.md (uses quota; needs TAVILY_API_KEY in .env).

Usage (from starter_v0/):
    python scripts/smoke_tools.py
    python scripts/smoke_tools.py --tools artifacts/tools.yaml --online
"""
from __future__ import annotations

import argparse
import glob
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from tools import TOOL_FUNCTIONS as T, load_tool_declarations  # noqa: E402
from tools.create_ticket.tool import TICKET_DIR  # noqa: E402

RESULTS: list[tuple[str, str, bool, str]] = []


def check(group: str, name: str, fn: Callable[[], Any], ok: Callable[[Any], bool]) -> None:
    try:
        value = fn()
        passed = bool(ok(value))
        detail = json.dumps(value, ensure_ascii=False, default=str)
    except Exception as exc:  # a crashing tool is a failed smoke check
        passed, detail = False, f"{type(exc).__name__}: {exc}"
    if len(detail) > 160:
        detail = detail[:157] + "..."
    RESULTS.append((group, name, passed, detail))


def ticket_files() -> set[str]:
    return {p.name for p in TICKET_DIR.glob("*.json")} if TICKET_DIR.exists() else set()


def schema_checks(tools_path: Path) -> None:
    decls = {d["name"]: d for d in load_tool_declarations(tools_path)}
    check("schema", "tools.yaml names == TOOL_FUNCTIONS", lambda: sorted(set(decls) ^ set(T)), lambda diff: diff == [])

    for name, decl in decls.items():
        if name not in T:
            continue
        params = decl.get("parameters", {})
        props = set(params.get("properties", {}))
        signature = set(inspect.signature(T[name]).parameters)
        check("schema", f"{name}: declared args accepted by implementation",
              lambda props=props, signature=signature: sorted(props - signature), lambda extra: extra == [])
        check("schema", f"{name}: required args are declared",
              lambda params=params, props=props: sorted(set(params.get("required", [])) - props), lambda missing: missing == [])

    def enum(tool: str, arg: str) -> set[str]:
        return set(decls[tool]["parameters"]["properties"][arg].get("enum", []))

    status = json.loads((ROOT / "helpdesk_data" / "service_status.json").read_text(encoding="utf-8"))["services"]
    assets = json.loads((ROOT / "helpdesk_data" / "assets.json").read_text(encoding="utf-8"))["assets"]
    kb_categories = {
        str(yaml.safe_load(Path(p).read_text(encoding="utf-8").split("---")[1]).get("category"))
        for p in glob.glob(str(ROOT / "helpdesk_data" / "knowledge_base" / "*.md"))
    }
    policy_areas = {
        str(yaml.safe_load(Path(p).read_text(encoding="utf-8").split("---")[1]).get("policy_area"))
        for p in glob.glob(str(ROOT / "company_policy" / "*-policy.md"))
    }
    diag_groups = {key for asset in assets for key in asset["diagnostics"]}

    check("schema", "check_service_status.service enum covers status data",
          lambda: sorted({s["service"] for s in status} - enum("check_service_status", "service")), lambda d: d == [])
    check("schema", "check_service_status.environment enum covers status data",
          lambda: sorted({s["environment"] for s in status} - enum("check_service_status", "environment")), lambda d: d == [])
    check("schema", "search_kb.category enum covers KB categories",
          lambda: sorted(kb_categories - enum("search_kb", "category")), lambda d: d == [])
    check("schema", "policy.policy_area enum covers policy files",
          lambda: sorted(policy_areas - enum("policy", "policy_area")), lambda d: d == [])
    check("schema", "inspect_device.check enum == diagnostics groups + all",
          lambda: sorted(enum("inspect_device", "check") ^ (diag_groups | {"all"})), lambda d: d == [])


def local_tool_checks() -> None:
    check("local", "clarify returns awaiting_user",
          lambda: T["clarify"]("Mã asset là gì?", "text"), lambda r: r.get("awaiting_user") is True)
    check("local", "search_kb returns results + trust_boundary",
          lambda: T["search_kb"]("VPN macOS certificate", "vpn", 2),
          lambda r: not r.get("error") and len(r.get("results") or []) > 0 and r.get("trust_boundary"))
    check("local", "search_kb moves injected lines to untrusted_text",
          lambda: [x["untrusted_text"] for x in T["search_kb"]("print queue troubleshooting safety sample", "printing", 3)["results"]],
          lambda lists: any(lists))
    check("local", "check_service_status has service/environment/status/checked_at",
          lambda: T["check_service_status"]("vpn", "production"),
          lambda r: all(r.get(k) for k in ("service", "environment", "status", "checked_at")))
    check("local", "check_service_status unknown service -> not_found",
          lambda: T["check_service_status"]("fax", "production"), lambda r: r.get("error") == "not_found")
    check("local", "inspect_device returns requested asset + group",
          lambda: T["inspect_device"]("LT-318", "vpn"),
          lambda r: r.get("asset_id") == "LT-318" and list(r.get("diagnostics", {})) == ["vpn"])
    check("local", "inspect_device unknown asset -> asset_not_found",
          lambda: T["inspect_device"]("LT-999", "all"), lambda r: r.get("error") == "asset_not_found")
    check("local", "lookup_user returns record + assigned assets",
          lambda: T["lookup_user"]("EMP-1007"),
          lambda r: r.get("employee", {}).get("employee_id") == "EMP-1007" and "assigned_assets" in r["employee"])
    check("local", "lookup_user unknown employee -> employee_not_found",
          lambda: T["lookup_user"]("EMP-9999"), lambda r: r.get("error") == "employee_not_found")
    check("local", "format_incident_report returns markdown + finding_count",
          lambda: T["format_incident_report"]([{"label": "VPN", "detail": "degraded"}], "brief", "VPN incident"),
          lambda r: r.get("markdown") and r.get("finding_count") == 1)
    check("local", "policy returns sections + source + trust_boundary",
          lambda: T["policy"]("dữ liệu nào được gửi ra external tool", "external_tools", 2),
          lambda r: not r.get("error") and len(r.get("results") or []) > 0 and r.get("trust_boundary")
          and all(x.get("source") for x in r["results"]))


def boundary_checks() -> None:
    check("boundary", "create_ticket confirmed=False -> needs_confirmation",
          lambda: T["create_ticket"]("VPN dry run", "low", "LT-204", False), lambda r: r.get("status") == "needs_confirmation")
    check("boundary", "create_ticket confirmed='true' (str) -> needs_confirmation",
          lambda: T["create_ticket"]("VPN", "low", "LT-204", "true"), lambda r: r.get("status") == "needs_confirmation")
    check("boundary", "create_ticket confirmed=1 (int) -> needs_confirmation",
          lambda: T["create_ticket"]("VPN", "low", "LT-204", 1), lambda r: r.get("status") == "needs_confirmation")
    check("boundary", "create_ticket confirmed={} (object) -> needs_confirmation",
          lambda: T["create_ticket"]("VPN", "low", "LT-204", {"confirmed": True}), lambda r: r.get("status") == "needs_confirmation")
    check("boundary", "create_ticket password in summary -> restricted_sensitive_data",
          lambda: T["create_ticket"]("password=Summer2026!", "low", "LT-204", True),
          lambda r: r.get("error") == "restricted_sensitive_data")
    check("boundary", "create_ticket OTP in summary -> restricted_sensitive_data",
          lambda: T["create_ticket"]("user gave otp là 123456", "low", "LT-204", True),
          lambda r: r.get("error") == "restricted_sensitive_data")
    check("boundary", "create_ticket malformed asset_id -> invalid_asset_id",
          lambda: T["create_ticket"]("VPN", "low", "LAPTOP-204", True), lambda r: r.get("error") == "invalid_asset_id")

    # Offline: every case below must be rejected before any HTTP request.
    check("boundary", "search_device_info asset ID in model -> restricted_internal_identifier",
          lambda: T["search_device_info"]("Lenovo", "ThinkPad T14 Gen 4 LT-204", "specs"),
          lambda r: r.get("error") == "restricted_internal_identifier")
    check("boundary", "search_device_info employee ID -> restricted_internal_identifier",
          lambda: T["search_device_info"]("Lenovo", "ThinkPad EMP-1001", "support"),
          lambda r: r.get("error") == "restricted_internal_identifier")
    check("boundary", "search_device_info empty model -> missing_public_product_identity",
          lambda: T["search_device_info"]("Lenovo", "", "specs"), lambda r: r.get("error") == "missing_public_product_identity")
    check("boundary", "search_device_info bad query_type -> invalid_query_type",
          lambda: T["search_device_info"]("Lenovo", "ThinkPad T14 Gen 4", "logs"), lambda r: r.get("error") == "invalid_query_type")
    check("boundary", "search_device_info valid input without key -> missing_api_key",
          lambda: T["search_device_info"]("Lenovo", "ThinkPad T14 Gen 4", "drivers", 2), lambda r: r.get("error") == "missing_api_key")


def online_check() -> None:
    from env_loader import load_lab_env

    load_lab_env(ROOT)
    if not os.getenv("TAVILY_API_KEY"):
        RESULTS.append(("online", "search_device_info Tavily call", False, "TAVILY_API_KEY is not set in .env"))
        return
    check("online", "search_device_info returns vendor-domain items",
          lambda: T["search_device_info"]("Lenovo", "ThinkPad T14 Gen 4", "drivers", 2),
          lambda r: not r.get("error") and len(r.get("items") or []) > 0
          and all(any(i["source"].endswith(d) for d in r["official_domains"]) for i in r["items"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tools", type=Path, default=ROOT / "artifacts" / "tools.yaml")
    parser.add_argument("--online", action="store_true", help="Also run the Tavily smoke call (uses quota).")
    args = parser.parse_args()

    os.environ.pop("TAVILY_API_KEY", None)
    tickets_before = ticket_files()

    schema_checks(args.tools)
    local_tool_checks()
    boundary_checks()
    new_tickets = sorted(ticket_files() - tickets_before)
    RESULTS.append(("boundary", "no ticket file written by smoke checks", not new_tickets, json.dumps(new_tickets)))
    if args.online:
        online_check()

    for group, name, passed, detail in RESULTS:
        print(f"[{'PASS' if passed else 'FAIL'}] {group:<8} {name}")
        if not passed:
            print(f"         -> {detail}")
    failed = sum(1 for _, _, passed, _ in RESULTS if not passed)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} checks passed ({args.tools})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
