import { CSSProperties, FormEvent, PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  AlertCircle,
  Bot,
  Check,
  ChevronDown,
  CircleDot,
  Clipboard,
  Download,
  ListChecks,
  Menu,
  MessageSquareText,
  PanelRight,
  Plus,
  Send,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Search,
  User,
  Wrench,
  X,
} from "lucide-react";
import { createSession, getConfig, getPreview, getTestCases, getTranscript, streamMessage } from "./api";
import type { AgentRound, AppConfig, ChatTurn, StreamEvent, TestCase, Transcript } from "./types";

const suggestions = [
  "Kiểm tra trạng thái VPN production giúp tôi.",
  "Máy tính của tôi không kết nối được Wi-Fi.",
  "Tìm hướng dẫn xử lý Outlook bị chậm.",
];

const statusLabels: Record<ChatTurn["status"], string> = {
  started: "Đang xử lý",
  answered: "Đã trả lời",
  waiting_for_user: "Chờ thông tin",
  max_tool_rounds: "Đạt giới hạn",
  provider_error: "Lỗi provider",
};

function shortHash(value: string) {
  return value.slice(0, 12);
}

function copyText(value: string) {
  void navigator.clipboard.writeText(value);
}

function providerLabel(provider: string) {
  if (provider === "ninerouter") return "9Router";
  if (provider === "demo") return "Offline demo";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function parseAssistantDisplay(text: string | null) {
  if (!text) return { reply: "", evidenceIds: [] as string[], jsonText: null as string | null };
  let candidate = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  if (candidate.startsWith("`") && candidate.endsWith("`")) candidate = candidate.slice(1, -1).trim();
  candidate = candidate.replace(/^json\s*(?=\{)/i, "");
  const objectStart = candidate.indexOf("{");
  const objectEnd = candidate.lastIndexOf("}");
  if (objectStart >= 0 && objectEnd > objectStart) candidate = candidate.slice(objectStart, objectEnd + 1);
  try {
    const payload = JSON.parse(candidate) as { reply?: unknown; evidence_ids?: unknown };
    if (typeof payload.reply === "string") {
      return {
        reply: payload.reply,
        evidenceIds: Array.isArray(payload.evidence_ids)
          ? payload.evidence_ids.filter((item): item is string => typeof item === "string")
          : [],
        jsonText: JSON.stringify(payload, null, 2),
      };
    }
  } catch {
    // Providers may return ordinary text for clarification or errors.
  }
  return { reply: text, evidenceIds: [] as string[], jsonText: null as string | null };
}

function applyStreamEvent(current: ChatTurn | null, event: StreamEvent): ChatTurn | null {
  if (event.type === "turn_started") return event.turn;
  if (event.type === "turn_finished") return event.turn;
  if (!current) return current;
  if (event.type === "round_started") {
    if (current.rounds.some((round) => round.round === event.round)) return current;
    return { ...current, rounds: [...current.rounds, { round: event.round, assistant_text: null, tool_calls: [], tool_results: [] }] };
  }
  if (event.type === "model_response") {
    return { ...current, rounds: current.rounds.map((round) => round.round === event.round_record.round ? event.round_record : round) };
  }
  if (event.type === "tool_completed") {
    return {
      ...current,
      tool_events: [...current.tool_events, event.event],
      rounds: current.rounds.map((round) => round.round === event.round
        ? { ...round, tool_results: [...round.tool_results, event.event] }
        : round),
    };
  }
  return current;
}

function ArtifactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="artifact-row">
      <div>
        <span>{label}</span>
        <code>{shortHash(value)}</code>
      </div>
      <button className="icon-button small" onClick={() => copyText(value)} aria-label={`Copy ${label}`}>
        <Clipboard size={14} />
      </button>
    </div>
  );
}

function ToolRound({ round }: { round: AgentRound }) {
  const [open, setOpen] = useState(true);
  const hasError = round.tool_results.some((event) => Boolean(event.result?.error));
  const display = parseAssistantDisplay(round.assistant_text);
  return (
    <div className={`trace-card ${hasError ? "trace-error" : ""}`}>
      <button className="trace-summary" onClick={() => setOpen((value) => !value)}>
        <span className="round-marker">{round.round}</span>
        <span className="trace-title">
          {round.tool_calls.length ? `${round.tool_calls.length} tool call${round.tool_calls.length > 1 ? "s" : ""}` : "Model response"}
        </span>
        {hasError ? <AlertCircle size={16} /> : <Check size={16} />}
        <ChevronDown className={open ? "rotate" : ""} size={16} />
      </button>
      {open && (
        <div className="trace-body">
          {round.assistant_text && (display.jsonText
            ? <pre className="model-response-json">{display.jsonText}</pre>
            : <div className="round-text markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{display.reply}</ReactMarkdown></div>)}
          {round.tool_results.map((event, index) => (
            <div className="tool-event" key={`${event.tool}-${index}`}>
              <div className="tool-name"><Wrench size={14} /> {event.tool}</div>
              <span className="json-label">Arguments</span>
              <pre>{JSON.stringify(event.args, null, 2)}</pre>
              <span className="json-label">Result</span>
              <pre>{JSON.stringify(event.result, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TracePanel({ turns, onClose }: { turns: ChatTurn[]; onClose?: () => void }) {
  return (
    <aside className="trace-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">Observability</span><h2>Tool trace</h2></div>
        {onClose && <button className="icon-button" onClick={onClose} aria-label="Đóng tool trace"><X size={18} /></button>}
      </div>
      <div className="trace-scroll">
        {!turns.length && (
          <div className="empty-trace">
            <Activity size={24} />
            <p>Tool calls và kết quả sẽ xuất hiện ở đây.</p>
          </div>
        )}
        {turns.map((turn) => (
          <section className="turn-trace" key={turn.turn_index}>
            <div className="turn-heading">
              <span>Turn {turn.turn_index}</span>
              <span className={`status-chip ${turn.status}`}>{statusLabels[turn.status]}</span>
            </div>
            {turn.rounds.map((round) => <ToolRound key={round.round} round={round} />)}
            {turn.error && <div className="inline-error"><AlertCircle size={15} />{turn.error}</div>}
          </section>
        ))}
      </div>
    </aside>
  );
}

function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [pendingTraceTurn, setPendingTraceTurn] = useState<ChatTurn | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [testCasesOpen, setTestCasesOpen] = useState(false);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [testCaseSearch, setTestCaseSearch] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(272);
  const [traceWidth, setTraceWidth] = useState(360);
  const chatEndRef = useRef<HTMLDivElement>(null);

  function beginResize(side: "sidebar" | "trace", event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = side === "sidebar" ? sidebarWidth : traceWidth;
    document.body.classList.add("is-resizing");

    const handleMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      if (side === "sidebar") {
        setSidebarWidth(Math.min(420, Math.max(210, startWidth + delta)));
      } else {
        setTraceWidth(Math.min(600, Math.max(280, startWidth - delta)));
      }
    };
    const handleUp = () => {
      document.body.classList.remove("is-resizing");
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  }

  function resizeWithKeyboard(side: "sidebar" | "trace", key: string) {
    if (key !== "ArrowLeft" && key !== "ArrowRight") return;
    const delta = key === "ArrowRight" ? 16 : -16;
    if (side === "sidebar") setSidebarWidth((width) => Math.min(420, Math.max(210, width + delta)));
    else setTraceWidth((width) => Math.min(600, Math.max(280, width - delta)));
  }

  useEffect(() => {
    getConfig()
      .then(async (value) => {
        setConfig(value);
        if (!value.live_available && !value.demo_mode) {
          const preview = await getPreview();
          setTranscript(preview.transcript);
        }
      })
      .catch((reason: Error) => setError(reason.message));
    getTestCases()
      .then((value) => setTestCases(value.cases))
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript?.turns, pendingMessage]);

  const isDemo = Boolean(config?.demo_mode);
  const isPreview = Boolean(config && !config.live_available && !config.demo_mode);
  const canChat = Boolean(config && (config.live_available || config.demo_mode));
  const turns = transcript?.turns ?? [];
  const visibleTraceTurns = pendingTraceTurn ? [...turns, pendingTraceTurn] : turns;
  const toolCount = useMemo(() => visibleTraceTurns.reduce((sum, turn) => sum + turn.tool_events.length, 0), [visibleTraceTurns]);
  const filteredTestCases = useMemo(() => {
    const query = testCaseSearch.trim().toLocaleLowerCase();
    if (!query) return testCases;
    return testCases.filter((testCase) => [
      testCase.id,
      testCase.skill,
      testCase.description,
      ...testCase.prompts,
      ...testCase.expected_tools,
    ].some((value) => value?.toLocaleLowerCase().includes(query)));
  }, [testCases, testCaseSearch]);

  async function ensureSession() {
    if (sessionId && transcript) return { id: sessionId, baseTranscript: transcript };
    const created = await createSession();
    setSessionId(created.session_id);
    setTranscript(created.transcript);
    return { id: created.session_id, baseTranscript: created.transcript };
  }

  async function handleSubmit(event?: FormEvent, suggestion?: string) {
    event?.preventDefault();
    const message = (suggestion ?? input).trim();
    if (!message || loading || !canChat) return;
    setInput("");
    setPendingMessage(message);
    setLoading(true);
    setError(null);
    try {
      const { id, baseTranscript } = await ensureSession();
      let completedTurn: ChatTurn | null = null;
      await streamMessage(id, message, (streamEvent) => {
        if (streamEvent.type === "stream_error") throw new Error(streamEvent.message);
        if (streamEvent.type === "turn_finished") completedTurn = streamEvent.turn;
        setPendingTraceTurn((current) => applyStreamEvent(current, streamEvent));
      });
      if (!completedTurn) throw new Error("Agent stream ended before the turn completed.");
      setTranscript((current) => {
        const activeTranscript = current ?? baseTranscript;
        return { ...activeTranscript, turns: [...activeTranscript.turns, completedTurn as ChatTurn] };
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể gửi tin nhắn.");
    } finally {
      setPendingMessage(null);
      setPendingTraceTurn(null);
      setLoading(false);
    }
  }

  async function newConversation() {
    setError(null);
    setInput("");
    setPendingMessage(null);
    setPendingTraceTurn(null);
    setSessionId(null);
    if (canChat) {
      setTranscript(null);
    } else {
      const preview = await getPreview();
      setTranscript(preview.transcript);
    }
    setSidebarOpen(false);
  }

  async function downloadTranscript() {
    if (!sessionId) return;
    const current = await getTranscript(sessionId);
    const blob = new Blob([JSON.stringify(current, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `${current.transcript_id}.transcript.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  }

  if (!config) {
    return (
      <main className="startup-screen">
        <div className="brand-mark"><Bot size={28} /></div>
        <p>{error ?? "Đang kết nối tới Helpdesk Agent…"}</p>
      </main>
    );
  }

  return (
    <div className="app-shell" style={{ "--sidebar-width": `${sidebarWidth}px`, "--trace-width": `${traceWidth}px` } as CSSProperties}>
      <aside className={`sidebar ${sidebarOpen ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Bot size={23} /></div>
          <div><strong>Octocat</strong><span>IT Helpdesk</span></div>
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)} aria-label="Đóng sidebar"><X size={18} /></button>
        </div>

        <button className="new-chat" onClick={newConversation}><Plus size={17} /> New conversation</button>

        <div className="sidebar-section">
          <span className="eyebrow">Agent runtime</span>
          <div className="runtime-card">
            <div className="runtime-row"><ServerCog size={17} /><span>Provider</span><strong>{providerLabel(config.provider)}</strong></div>
            <div className="runtime-row"><Sparkles size={17} /><span>Model</span><strong>{config.model}</strong></div>
            <div className="runtime-row"><MessageSquareText size={17} /><span>History</span><strong>{config.default_history_window} turns</strong></div>
            <div className="runtime-row"><CircleDot size={17} /><span>Max rounds</span><strong>{config.default_max_tool_rounds}</strong></div>
          </div>
        </div>

        <div className="sidebar-section artifact-section">
          <span className="eyebrow">Artifact identity</span>
          <div className="version-badge">{config.version}</div>
          <ArtifactRow label="Prompt hash" value={config.prompt_hash} />
          <ArtifactRow label="Tools hash" value={config.tools_hash} />
          <p className="artifact-full">{config.artifact_version}</p>
        </div>

        <div className="sidebar-footer">
          <ShieldCheck size={18} />
          <div><strong>Safety boundaries active</strong><span>Internal data stays local</span></div>
        </div>
        <button className="resize-handle sidebar-resizer" aria-label="Thay đổi chiều rộng sidebar" onPointerDown={(event) => beginResize("sidebar", event)} onDoubleClick={() => setSidebarWidth(272)} onKeyDown={(event) => resizeWithKeyboard("sidebar", event.key)} />
      </aside>

      {sidebarOpen && <button className="mobile-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar" />}

      <main className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} aria-label="Mở sidebar"><Menu size={20} /></button>
          <div className="title-block"><h1>IT Helpdesk Agent</h1><span>Tool-calling workspace</span></div>
          <button className="test-cases-button" onClick={() => setTestCasesOpen(true)}><ListChecks size={16} /><span>Test cases</span><b>{testCases.length}</b></button>
          <div className={`connection-pill ${config.live_available ? "online" : "preview"}`}>
            <span className="connection-dot" />
            {config.live_available ? "Online" : isDemo ? "Demo offline" : "Preview mode"}
          </div>
          <button className="icon-button trace-mobile" onClick={() => setTraceOpen(true)} aria-label="Mở tool trace"><PanelRight size={20} /></button>
        </header>

        {isPreview && (
          <div className="preview-banner">
            <AlertCircle size={18} />
            <div><strong>Preview mẫu — không phải evidence</strong><span>Thêm GEMINI_API_KEY vào .env để bắt đầu live chat.</span></div>
          </div>
        )}

        {isDemo && (
          <div className="preview-banner demo-banner">
            <Activity size={18} />
            <div><strong>Demo offline — local tools đang hoạt động</strong><span>Rule router thay model; transcript này không được tính là evidence của provider.</span></div>
          </div>
        )}

        <section className="chat-scroll">
          {!turns.length && (
            <div className="welcome-card">
              <div className="welcome-icon"><Sparkles size={26} /></div>
              <span className="eyebrow">Service desk copilot</span>
              <h2>Hôm nay bạn cần hỗ trợ gì?</h2>
              <p>Kiểm tra dịch vụ, chẩn đoán thiết bị và tìm hướng dẫn nội bộ với tool trace minh bạch.</p>
              <div className="suggestions">
                {suggestions.map((item) => (
                  <button key={item} disabled={isPreview} onClick={(event) => void handleSubmit(event, item)}>{item}<Send size={15} /></button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => {
            const display = parseAssistantDisplay(turn.assistant_text);
            return (
              <div className="conversation-turn" key={turn.turn_index}>
                <div className="message user-message"><div className="avatar"><User size={17} /></div><div><span className="message-author">Bạn</span><p>{turn.user}</p></div></div>
                <div className="message agent-message"><div className="avatar"><Bot size={17} /></div><div><span className="message-author">Helpdesk Agent</span><div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a> }}>{display.reply}</ReactMarkdown></div>{display.evidenceIds.length > 0 && <div className="evidence-list">{display.evidenceIds.map((id) => <code key={id}>{id}</code>)}</div>}<span className={`status-chip ${turn.status}`}>{statusLabels[turn.status]}</span></div></div>
              </div>
            );
          })}

          {pendingMessage && (
            <div className="conversation-turn">
              <div className="message user-message"><div className="avatar"><User size={17} /></div><div><span className="message-author">Bạn</span><p>{pendingMessage}</p></div></div>
              <div className="message agent-message loading-message"><div className="avatar"><Bot size={17} /></div><div><span className="message-author">Helpdesk Agent</span><div className="typing"><i /><i /><i /></div></div></div>
            </div>
          )}
          {error && <div className="chat-error"><AlertCircle size={17} />{error}</div>}
          <div ref={chatEndRef} />
        </section>

        <footer className="composer-area">
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSubmit();
                }
              }}
              disabled={isPreview || loading}
              placeholder={isPreview ? "Cần GEMINI_API_KEY để bắt đầu live chat" : "Mô tả vấn đề IT của bạn…"}
              rows={1}
            />
            <button className="send-button" type="submit" disabled={!input.trim() || loading || isPreview} aria-label="Gửi tin nhắn"><Send size={18} /></button>
          </form>
          <div className="composer-meta">
            <span>{toolCount} tool calls trong phiên</span>
            {sessionId && <button onClick={() => void downloadTranscript()}><Download size={14} /> Download transcript</button>}
          </div>
        </footer>
      </main>

      <div className="desktop-trace"><button className="resize-handle trace-resizer" aria-label="Thay đổi chiều rộng Tool trace" onPointerDown={(event) => beginResize("trace", event)} onDoubleClick={() => setTraceWidth(360)} onKeyDown={(event) => resizeWithKeyboard("trace", event.key)} /><TracePanel turns={visibleTraceTurns} /></div>
      {traceOpen && <div className="trace-drawer"><button className="mobile-backdrop" onClick={() => setTraceOpen(false)} /><TracePanel turns={visibleTraceTurns} onClose={() => setTraceOpen(false)} /></div>}
      {testCasesOpen && (
        <div className="test-cases-overlay">
          <button className="test-cases-backdrop" onClick={() => setTestCasesOpen(false)} aria-label="Đóng test cases" />
          <section className="test-cases-panel" aria-label="Test cases">
            <div className="test-cases-header">
              <div><span className="eyebrow">Evaluation prompts</span><h2>Test cases <small>{filteredTestCases.length}/{testCases.length}</small></h2></div>
              <button className="icon-button" onClick={() => setTestCasesOpen(false)} aria-label="Đóng test cases"><X size={18} /></button>
            </div>
            <label className="test-search"><Search size={16} /><input value={testCaseSearch} onChange={(event) => setTestCaseSearch(event.target.value)} placeholder="Tìm ID, prompt hoặc tool…" /></label>
            <div className="test-cases-scroll">
              {filteredTestCases.map((testCase) => (
                <article className="test-case-card" key={testCase.id}>
                  <div className="test-case-meta"><strong>{testCase.id}</strong><span>{testCase.difficulty}</span><span>{testCase.prompts.length > 1 ? `${testCase.prompts.length} turns` : "single turn"}</span></div>
                  {testCase.description && <p>{testCase.description}</p>}
                  {testCase.expected_tools.length > 0 && <div className="expected-tools">Expected: {testCase.expected_tools.map((tool) => <code key={tool}>{tool}</code>)}</div>}
                  <div className="test-prompts">
                    {testCase.prompts.map((prompt, index) => (
                      <button key={`${testCase.id}-${index}`} disabled={!canChat || loading} onClick={() => { setTestCasesOpen(false); void handleSubmit(undefined, prompt); }}>
                        <span>{testCase.prompts.length > 1 ? `Turn ${index + 1}` : "Run"}</span><p>{prompt}</p><Send size={14} />
                      </button>
                    ))}
                  </div>
                </article>
              ))}
              {!filteredTestCases.length && <div className="empty-test-cases">Không tìm thấy test case phù hợp.</div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
