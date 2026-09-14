from __future__ import annotations

import json
import re
from typing import Any

from providers.base import ModelResponse, ToolCall


ASSET_ID = re.compile(r"\b(?:LT|DT|MB|PR|RM)-\d+\b", re.IGNORECASE)
CONFIRMATIONS = {"yes", "y", "ok", "okay", "confirm", "confirmed", "xác nhận", "đồng ý", "tạo đi"}


def _tool_events(content: str) -> list[dict[str, Any]]:
    if not content.startswith("TOOL_RESULTS_JSON:"):
        return []
    payload = content.removeprefix("TOOL_RESULTS_JSON:").split("\n\nUse only", 1)[0]
    try:
        value = json.loads(payload)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


class DemoProvider:
    """Deterministic offline router for UI demos; local tools still execute normally."""

    default_model = "local-rule-router"

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        tool_choice: Any | None = None,
    ) -> ModelResponse:
        latest = messages[-1]["content"]
        events = _tool_events(latest)
        if events:
            return ModelResponse(text=self._answer_from_tool(events[-1]))

        user_text = latest.strip()
        folded = user_text.casefold()
        conversation = "\n".join(message["content"] for message in messages[-6:]).casefold()
        asset_match = ASSET_ID.search(user_text)

        if folded in CONFIRMATIONS and "xác nhận tạo ticket" in conversation:
            previous = next(
                (message["content"] for message in reversed(messages[:-1]) if message["role"] == "user"),
                "Sự cố IT cần hỗ trợ",
            )
            previous_asset = ASSET_ID.search(conversation)
            return ModelResponse(tool_calls=[ToolCall("create_ticket", {
                "summary": previous[:500],
                "priority": "medium",
                "asset_id": previous_asset.group(0).upper() if previous_asset else "",
                "confirmed": True,
            })])

        if "ticket" in folded or "phiếu hỗ trợ" in folded:
            return ModelResponse(tool_calls=[ToolCall("clarify", {
                "question": "Mình sẽ tạo ticket mức medium từ mô tả hiện tại. Bạn có xác nhận tạo ticket không?",
                "response_type": "yes_no",
                "options": ["Xác nhận", "Hủy"],
            })])

        if asset_match:
            check = "network" if any(word in folded for word in ("wifi", "wi-fi", "mạng", "network")) else "all"
            return ModelResponse(tool_calls=[ToolCall("inspect_device", {
                "asset_id": asset_match.group(0).upper(),
                "check": check,
            })])

        if any(word in folded for word in ("vpn", "email", "sso", "wifi", "wi-fi", "printing", "máy in")):
            if any(word in folded for word in ("trạng thái", "status", "production", "staging", "dịch vụ")) or "vpn" in folded:
                service = "printing" if "máy in" in folded else "wifi" if "wi-fi" in folded else next(
                    (name for name in ("vpn", "email", "sso", "wifi", "printing") if name in folded),
                    "wifi",
                )
                environment = "staging" if "staging" in folded else "production"
                return ModelResponse(tool_calls=[ToolCall("check_service_status", {
                    "service": service,
                    "environment": environment,
                })])
            return ModelResponse(tool_calls=[ToolCall("clarify", {
                "question": "Bạn cho mình mã asset của thiết bị (ví dụ LT-204) để kiểm tra đúng máy nhé.",
                "response_type": "text",
                "options": [],
            })])

        category = "email" if "outlook" in folded else "all"
        return ModelResponse(tool_calls=[ToolCall("search_kb", {
            "query": user_text,
            "category": category,
            "top_k": 3,
        })])

    @staticmethod
    def _answer_from_tool(event: dict[str, Any]) -> str:
        tool = event.get("tool")
        result = event.get("result") or {}
        if result.get("error"):
            return f"Tool {tool} trả về lỗi `{result['error']}`. Bạn kiểm tra lại thông tin đầu vào nhé."
        if tool == "check_service_status":
            status = result.get("status", "unknown")
            incident = result.get("incident") or "Không có incident đang mở."
            workaround = result.get("workaround") or "Chưa cần workaround."
            return f"Dịch vụ {result.get('service')} ({result.get('environment')}) hiện **{status}**. {incident} Hướng xử lý tạm thời: {workaround}"
        if tool == "inspect_device":
            diagnostics = result.get("diagnostics") or {}
            details = "; ".join(f"{key}: {value}" for key, value in diagnostics.items())
            return f"Kết quả kiểm tra {result.get('asset_id')}: {details or 'không có dữ liệu chẩn đoán'}."
        if tool == "search_kb":
            hits = result.get("results") or []
            if not hits:
                return "Không tìm thấy hướng dẫn phù hợp trong knowledge base. Bạn mô tả thêm lỗi hoặc cung cấp mã asset nhé."
            hit = hits[0]
            return f"Mình tìm thấy **{hit.get('title')}** trong knowledge base:\n\n{hit.get('content', '')[:900]}"
        if tool == "create_ticket":
            return f"Đã tạo ticket **{result.get('ticket_id')}** thành công."
        return f"Tool {tool} đã chạy xong. Kết quả chi tiết nằm trong Tool trace."
