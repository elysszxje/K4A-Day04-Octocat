import type { AppConfig, ChatTurn, StreamEvent, Transcript } from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const getConfig = () => request<AppConfig>("/api/config");

export const getPreview = () =>
  request<{ is_evidence: false; transcript: Transcript }>("/api/preview");

export const createSession = () =>
  request<{ session_id: string; transcript: Transcript }>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ history_window: 5, max_tool_rounds: 4 }),
  });

export const sendMessage = (sessionId: string, message: string) =>
  request<{ session_id: string; turn: ChatTurn }>(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });

export async function streamMessage(
  sessionId: string,
  message: string,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(`/api/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error("Streaming response body is unavailable.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as StreamEvent);
    }
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as StreamEvent);
}

export const getTranscript = (sessionId: string) =>
  request<Transcript>(`/api/sessions/${sessionId}/transcript`);
