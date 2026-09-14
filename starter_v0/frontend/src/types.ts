export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface ToolEvent {
  tool: string;
  args: Record<string, JsonValue>;
  result: Record<string, JsonValue>;
}

export interface AgentRound {
  round: number;
  assistant_text: string | null;
  tool_calls: Array<{ name: string; args: Record<string, JsonValue> }>;
  tool_results: ToolEvent[];
}

export interface ChatTurn {
  turn_index: number;
  started_at: string;
  ended_at?: string;
  user: string;
  assistant_text: string | null;
  status: "started" | "answered" | "waiting_for_user" | "max_tool_rounds" | "provider_error";
  error?: string;
  rounds: AgentRound[];
  tool_events: ToolEvent[];
}

export interface Transcript {
  transcript_id: string;
  version: string;
  artifact_version: string;
  prompt_hash: string;
  tools_hash: string;
  provider: string;
  model: string | null;
  history_window: number;
  max_tool_rounds: number;
  created_at: string;
  updated_at: string;
  turns: ChatTurn[];
  is_evidence?: boolean;
}

export interface AppConfig {
  provider: string;
  model: string;
  live_available: boolean;
  demo_mode: boolean;
  version: string;
  artifact_version: string;
  prompt_hash: string;
  tools_hash: string;
  default_history_window: number;
  default_max_tool_rounds: number;
}

export type StreamEvent =
  | { type: "turn_started"; turn: ChatTurn }
  | { type: "round_started"; round: number }
  | { type: "model_response"; round_record: AgentRound }
  | { type: "tool_started"; round: number; tool: string; args: Record<string, JsonValue> }
  | { type: "tool_completed"; round: number; event: ToolEvent }
  | { type: "turn_finished"; turn: ChatTurn }
  | { type: "stream_error"; message: string };

export interface TestCase {
  id: string;
  suite: string | null;
  failure_type: string | null;
  difficulty: string | null;
  skill: string | null;
  description: string | null;
  prompts: string[];
  expected_tools: string[];
}
