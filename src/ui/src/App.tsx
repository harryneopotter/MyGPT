import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type ChatMessage = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  corrects_message_id?: number | null;
};

type Conversation = {
  id: number;
  title: string | null;
  created_at: string;
  message_count: number;
};

type PreferenceProposal = {
  id: number;
  conversation_id: number;
  key: string;
  value: string;
  proposal_text: string;
  rationale?: string | null;
  status: "pending" | "approved" | "rejected" | "dismissed";
  created_at: string;
  decided_at?: string | null;
  causality_message_id?: number | null;
  assistant_message_id?: number | null;
};

type StoredPreference = {
  id: number;
  key: string;
  value: string;
  scope: string;
  created_at: string;
  approved_event_id?: number | null;
  source_proposal_id?: number | null;
};

type PreferencesResponse = {
  scope: string;
  reset: { id: number; created_at: string; reset_event_id: number | null } | null;
  preferences: StoredPreference[];
};

type ToolDefinition = {
  tool_id: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  requires_confirmation: boolean;
  requires_network: boolean;
};

type ToolRunResponse = {
  success: boolean;
  output?: Record<string, unknown> | null;
  error?: string | null;
};

type ModelInfo = {
  model_url: string;
};

type ToolFormState = {
  path: string;
  recursive: boolean;
  max_entries: string;
  max_bytes: string;
  pattern: string;
  max_matches: string;
  mode: "overwrite" | "append";
  content: string;
  staged: boolean;
  ref: string;
  query: string;
  max_rows: string;
  url: string;
  command: string;
  args: string;
  patch: string;
};

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

function parseSseChunk(chunk: string): Array<Record<string, unknown>> {
  const events: Array<Record<string, unknown>> = [];
  const parts = chunk.split("\n\n");
  for (const part of parts) {
    const line = part.trim();
    if (!line.startsWith("data:")) continue;
    const jsonStr = line.slice("data:".length).trim();
    if (!jsonStr) continue;
    try {
      const obj = JSON.parse(jsonStr) as Record<string, unknown>;
      events.push(obj);
    } catch {
      // Ignore malformed events.
    }
  }
  return events;
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);   
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [proposal, setProposal] = useState<PreferenceProposal | null>(null);
  const [preferences, setPreferences] = useState<PreferencesResponse | null>(null);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [selectedToolId, setSelectedToolId] = useState<string>("");
  const [toolInput, setToolInput] = useState<string>("{}");
  const [toolRunResult, setToolRunResult] = useState<ToolRunResponse | null>(null);
  const [toolError, setToolError] = useState<string | null>(null);
  const [toolConfirmed, setToolConfirmed] = useState(false);
  const [toolCausalityMessageId, setToolCausalityMessageId] = useState<number | "">("");
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [modelUrlInput, setModelUrlInput] = useState("");
  const [modelError, setModelError] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<
    Array<{ key: string; display: string; notes?: string }>
  >([]);
  const [selectedModelKey, setSelectedModelKey] = useState("");
  const [modelSwitchConfirmed, setModelSwitchConfirmed] = useState(false);
  const [serviceStatus, setServiceStatus] = useState<{
    backend: string;
    llama: { url: string; running: boolean };
  } | null>(null);
  const [logData, setLogData] = useState<{ app_log: string[]; error_log: string[] } | null>(null);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [llamaActionConfirm, setLlamaActionConfirm] = useState(false);
  const [logLevel, setLogLevel] = useState("");
  const [logContains, setLogContains] = useState("");
  const [eventType, setEventType] = useState("");
  const [eventsData, setEventsData] = useState<
    Array<{
      id: number;
      type: string;
      payload_json: string;
      created_at: string;
      conversation_id?: number | null;
      causality_message_id?: number | null;
    }>
  >([]);
  const [toolForm, setToolForm] = useState<ToolFormState>({
    path: ".",
    recursive: false,
    max_entries: "2000",
    max_bytes: "200000",
    pattern: "",
    max_matches: "2000",
    mode: "overwrite",
    content: "",
    staged: false,
    ref: "HEAD",
    query: "",
    max_rows: "200",
    url: "",
    command: "",
    args: "",
    patch: "",
  });
  const abortRef = useRef<AbortController | null>(null);
  const canSend = useMemo(() => input.trim().length > 0 && !isStreaming, [input, isStreaming]);

  const loadPreferences = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/preferences?scope=global`);
      const body = (await res.json()) as PreferencesResponse;
      setPreferences(body);
    } catch {
      setPreferences(null);
    }
  };

  const loadProposal = async (conversationId: number) => {
    try {
      const res = await fetch(
        `${BACKEND_URL}/preference-proposals?conversation_id=${conversationId}&status=pending`,
      );
      const body = (await res.json()) as { proposals: PreferenceProposal[] };
      setProposal(body.proposals[0] ?? null);
    } catch {
      setProposal(null);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const convRes = await fetch(`${BACKEND_URL}/conversations`);
        const convs = (await convRes.json()) as Conversation[];
        setConversations(convs);

        let selectedId = convs[0]?.id ?? null;
        if (selectedId == null) {
          const created = await fetch(`${BACKEND_URL}/conversations`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: "Chat" }),
          });
          const createdBody = (await created.json()) as { id: number };
          selectedId = createdBody.id;
          const convRes2 = await fetch(`${BACKEND_URL}/conversations`);
          setConversations((await convRes2.json()) as Conversation[]);
        }

        setActiveConversationId(selectedId);
        void loadPreferences();
        const toolRes = await fetch(`${BACKEND_URL}/tools`);
        const toolBody = (await toolRes.json()) as { tools: ToolDefinition[] };
        setTools(toolBody.tools ?? []);
        if (toolBody.tools?.length) {
          setSelectedToolId((prev) => prev || toolBody.tools[0].tool_id);
        }
        const modelRes = await fetch(`${BACKEND_URL}/model`);
        const modelBody = (await modelRes.json()) as ModelInfo;
        setModelInfo(modelBody);
        setModelUrlInput(modelBody.model_url ?? "");
        const modelOptRes = await fetch(`${BACKEND_URL}/model/options`);
        const modelOptBody = (await modelOptRes.json()) as {
          models?: Array<{ key: string; display: string; notes?: string }>;
          default_model_key?: string;
        };
        const opts = modelOptBody.models ?? [];
        setModelOptions(opts);
        setSelectedModelKey(modelOptBody.default_model_key ?? opts[0]?.key ?? "");
        const statusRes = await fetch(`${BACKEND_URL}/services/status`);
        const statusBody = (await statusRes.json()) as {
          backend: string;
          llama: { url: string; running: boolean };
        };
        setServiceStatus(statusBody);
      } catch {
        setConversations([]);
        setActiveConversationId(null);
        setMessages([]);
        setPreferences(null);
        setTools([]);
        setModelInfo(null);
        setModelUrlInput("");
        setModelOptions([]);
        setSelectedModelKey("");
        setServiceStatus(null);
      }
    };
    void load();
  }, []);

  useEffect(() => {
    if (activeConversationId == null) return;
    fetch(`${BACKEND_URL}/messages?conversation_id=${activeConversationId}`)
      .then((res) => res.json())
      .then((data: ChatMessage[]) => setMessages(data))
      .catch(() => setMessages([]));
    void loadProposal(activeConversationId);
  }, [activeConversationId]);

  const applyToolForm = () => {
    const buildNumber = (value: string) => {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : undefined;
    };
    let payload: Record<string, unknown> = {};
    switch (selectedToolId) {
      case "list_dir":
        payload = {
          path: toolForm.path || ".",
          recursive: toolForm.recursive,
          max_entries: buildNumber(toolForm.max_entries),
        };
        break;
      case "read_file":
        payload = {
          path: toolForm.path,
          max_bytes: buildNumber(toolForm.max_bytes),
        };
        break;
      case "search_text":
        payload = {
          pattern: toolForm.pattern,
          path: toolForm.path || ".",
          max_matches: buildNumber(toolForm.max_matches),
        };
        break;
      case "stat_path":
        payload = {
          path: toolForm.path,
        };
        break;
      case "write_file":
        payload = {
          path: toolForm.path,
          content: toolForm.content,
          mode: toolForm.mode,
        };
        break;
      case "git_diff":
        payload = {
          staged: toolForm.staged,
          path: toolForm.path || undefined,
        };
        break;
      case "git_show":
        payload = {
          ref: toolForm.ref,
        };
        break;
      case "sql_query":
        payload = {
          query: toolForm.query,
          max_rows: buildNumber(toolForm.max_rows),
        };
        break;
      case "open_url":
        payload = {
          url: toolForm.url,
        };
        break;
      case "run_command":
        payload = {
          command: toolForm.command,
          args: toolForm.args
            ? toolForm.args.split(",").map((arg) => arg.trim()).filter(Boolean)
            : [],
        };
        break;
      case "apply_patch":
        payload = {
          patch: toolForm.patch,
        };
        break;
      default:
        payload = {};
        break;
    }
    setToolInput(JSON.stringify(payload, null, 2));
  };

  useEffect(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === "user" && m.id != null);
    if (lastUser?.id != null) {
      setToolCausalityMessageId(lastUser.id);
    }
  }, [messages]);

  const newChat = async () => {
    if (isStreaming) return;
    const res = await fetch(`${BACKEND_URL}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: null }),
    });
    const body = (await res.json()) as { id: number };
    const convRes = await fetch(`${BACKEND_URL}/conversations`);
    setConversations((await convRes.json()) as Conversation[]);
    setActiveConversationId(body.id);
    setMessages([]);
    setProposal(null);
  };

  const approveProposal = async () => {
    if (proposal == null) return;
    await fetch(`${BACKEND_URL}/preference-proposals/${proposal.id}/approve`, {
      method: "POST",
    });
    if (activeConversationId != null) void loadProposal(activeConversationId);
    void loadPreferences();
  };

  const rejectProposal = async () => {
    if (proposal == null) return;
    await fetch(`${BACKEND_URL}/preference-proposals/${proposal.id}/reject`, {
      method: "POST",
    });
    if (activeConversationId != null) void loadProposal(activeConversationId);
  };

  const resetPreferences = async () => {
    if (!confirm("Reset approved preferences back to baseline?")) return;
    await fetch(`${BACKEND_URL}/preferences/reset?scope=global`, { method: "POST" });
    void loadPreferences();
  };

  const applyModelUrl = async () => {
    if (!modelUrlInput.trim()) {
      setModelError("Model URL is required.");
      return;
    }
    try {
      const res = await fetch(`${BACKEND_URL}/model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_url: modelUrlInput.trim() }),
      });
      const body = (await res.json()) as ModelInfo;
      setModelInfo(body);
      setModelUrlInput(body.model_url ?? "");
      setModelError(null);
    } catch {
      setModelError("Failed to update model URL.");
    }
  };

  const switchModel = async () => {
    if (!selectedModelKey) {
      setModelError("Select a model to switch.");
      return;
    }
    if (!modelSwitchConfirmed) {
      setModelError("Confirm the model switch before proceeding.");
      return;
    }
    try {
      const res = await fetch(`${BACKEND_URL}/model/switch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_key: selectedModelKey, confirmed: true }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail);
      }
      const body = (await res.json()) as { model_url: string };
      setModelInfo({ model_url: body.model_url });
      setModelUrlInput(body.model_url ?? "");
      setModelError(null);
    } catch (err) {
      setModelError(err instanceof Error ? err.message : "Model switch failed.");
    }
  };

  const refreshStatus = async () => {
    try {
      const statusRes = await fetch(`${BACKEND_URL}/services/status`);
      const statusBody = (await statusRes.json()) as {
        backend: string;
        llama: { url: string; running: boolean };
      };
      setServiceStatus(statusBody);
    } catch {
      setServiceStatus(null);
    }
  };

  const loadLogs = async () => {
    try {
      const params = new URLSearchParams();
      params.set("limit", "300");
      if (logLevel) params.set("level", logLevel);
      if (logContains) params.set("contains", logContains);
      const res = await fetch(`${BACKEND_URL}/logs?${params.toString()}`);
      const body = (await res.json()) as { app_log: string[]; error_log: string[] };
      setLogData(body);
    } catch {
      setLogData(null);
    }
  };

  const loadEvents = async () => {
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (eventType) params.set("event_type", eventType);
      if (activeConversationId != null) {
        params.set("conversation_id", String(activeConversationId));
      }
      const res = await fetch(`${BACKEND_URL}/events?${params.toString()}`);
      const body = (await res.json()) as {
        events: Array<{
          id: number;
          type: string;
          payload_json: string;
          created_at: string;
          conversation_id?: number | null;
          causality_message_id?: number | null;
        }>;
      };
      setEventsData(body.events ?? []);
    } catch {
      setEventsData([]);
    }
  };

  const startLlama = async () => {
    if (!llamaActionConfirm) {
      setServiceError("Confirm the action before starting llama.cpp.");
      return;
    }
    try {
      const res = await fetch(`${BACKEND_URL}/services/llama/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true, model_key: selectedModelKey || undefined }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail);
      }
      setServiceError(null);
      await refreshStatus();
    } catch (err) {
      setServiceError(err instanceof Error ? err.message : "Failed to start llama.cpp.");
    }
  };

  const stopLlama = async () => {
    if (!llamaActionConfirm) {
      setServiceError("Confirm the action before stopping llama.cpp.");
      return;
    }
    try {
      const res = await fetch(`${BACKEND_URL}/services/llama/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail);
      }
      setServiceError(null);
      await refreshStatus();
    } catch (err) {
      setServiceError(err instanceof Error ? err.message : "Failed to stop llama.cpp.");
    }
  };

  const runTool = async () => {
    if (!selectedToolId) return;
    if (!toolCausalityMessageId) {
      setToolError("Select a user message to attribute this tool run.");
      return;
    }
    let parsedInput: Record<string, unknown> = {};
    if (toolInput.trim().length > 0) {
      try {
        parsedInput = JSON.parse(toolInput) as Record<string, unknown>;
      } catch {
        setToolError("Tool input must be valid JSON.");
        return;
      }
    }
    setToolError(null);
    setToolRunResult(null);
    try {
      const res = await fetch(`${BACKEND_URL}/tools/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_id: selectedToolId,
          tool_input: parsedInput,
          conversation_id: activeConversationId,
          causality_message_id: toolCausalityMessageId,
          confirmed: toolConfirmed,
        }),
      });
      const body = (await res.json()) as ToolRunResponse;
      setToolRunResult(body);
      if (!body.success) {
        setToolError(body.error ?? "Tool run failed.");
      }
    } catch {
      setToolError("Tool run failed.");
    }
  };

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!canSend) return;
    if (activeConversationId == null) return;

    const userContent = input.trim();
    setInput("");
    setIsStreaming(true);

    setMessages((prev) => [...prev, { role: "user", content: userContent }, { role: "assistant", content: "" }]);

    try {
      const controller = new AbortController();
      abortRef.current = controller;
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: userContent, conversation_id: activeConversationId }),
        signal: controller.signal,
      });

      if (!res.body) throw new Error("Missing response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const evt of parseSseChunk(chunk)) {
          const maybeProposal = evt.proposal as PreferenceProposal | undefined;
          if (maybeProposal && typeof maybeProposal === "object") {
            setProposal(maybeProposal);
          }
          if (evt.done === true) {
            setIsStreaming(false);
            fetch(`${BACKEND_URL}/messages?conversation_id=${activeConversationId}`)
              .then((r) => r.json())
              .then((data: ChatMessage[]) => setMessages(data))
              .catch(() => undefined);
            void loadProposal(activeConversationId);
            return;
          }
          const token = typeof evt.token === "string" ? evt.token : "";
          if (!token) continue;
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, content: last.content + token };
            }
            return next;
          });
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        fetch(`${BACKEND_URL}/messages?conversation_id=${activeConversationId}`)
          .then((r) => r.json())
          .then((data: ChatMessage[]) => setMessages(data))
          .catch(() => undefined);
        return;
      }
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant" && last.content.trim().length === 0) {
          next[next.length - 1] = { ...last, content: "(error) Failed to stream response from backend." };
        }
        return next;
      });
    } finally {
      abortRef.current = null;
      setIsStreaming(false);
    }
  };

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginTop: 0 }}>Logical Low-Friction AI Chat</h1>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontWeight: 700 }}>Chat</span>
          <select
            value={activeConversationId ?? ""}
            disabled={isStreaming}
            onChange={(e) => setActiveConversationId(Number(e.target.value))}
          >
            {conversations.map((c) => (
              <option key={c.id} value={c.id}>
                {(c.title && c.title.trim()) || `Conversation ${c.id}`} ({c.message_count})
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={newChat} disabled={isStreaming}>
          New Chat
        </button>
        <button
          type="button"
          onClick={() => abortRef.current?.abort()}
          disabled={!isStreaming}
          style={{ marginLeft: "auto" }}
        >
          Stop
        </button>
      </div>

      <div style={{ border: "1px solid #ccc", borderRadius: 6, padding: 12, height: 420, overflowY: "auto" }}>
        {messages.length === 0 ? (
          <div style={{ opacity: 0.7 }}>No messages yet.</div>
        ) : (
          messages.map((m, idx) => (
            <div key={m.id ?? idx} style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 700 }}>{m.role}</div>
              <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
            </div>
          ))
        )}
      </div>

      {proposal?.status === "pending" && !isStreaming ? (
        <div
          style={{
            marginTop: 12,
            border: "1px solid #ddd",
            borderRadius: 6,
            padding: 12,
            background: "#fafafa",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>
            Preference proposal (optional)
          </div>
          <div style={{ marginBottom: 6 }}>{proposal.proposal_text}</div>
          {proposal.rationale ? (
            <div style={{ opacity: 0.8, marginBottom: 10 }}>{proposal.rationale}</div>
          ) : null}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={approveProposal}>
              Approve
            </button>
            <button type="button" onClick={rejectProposal}>
              Reject
            </button>
          </div>
        </div>
      ) : null}

      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 6, padding: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ fontWeight: 700 }}>Preferences</div>
          <button type="button" onClick={loadPreferences} disabled={isStreaming} style={{ marginLeft: "auto" }}>
            Refresh
          </button>
          <button type="button" onClick={resetPreferences} disabled={isStreaming}>
            Reset
          </button>
        </div>
        {preferences?.preferences?.length ? (
          <div style={{ marginTop: 8, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
            {Object.entries(
              preferences.preferences.reduce<Record<string, string>>((acc, p) => {
                acc[p.key] = p.value;
                return acc;
              }, {}),
            ).map(([key, value]) => (
              <div key={key}>
                {key}={value}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ marginTop: 8, opacity: 0.7 }}>No approved preferences.</div>
        )}
      </div>

      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 6, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Model</div>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
          <label>Current model URL</label>
          <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
            {modelInfo?.model_url ?? "unknown"}
          </div>
          <label>Set model URL</label>
          <input
            value={modelUrlInput}
            onChange={(e) => setModelUrlInput(e.target.value)}
            disabled={isStreaming}
          />
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button type="button" onClick={applyModelUrl} disabled={isStreaming}>
            Apply
          </button>
          <button
            type="button"
            onClick={() => setModelUrlInput(modelInfo?.model_url ?? "")}
            disabled={isStreaming}
          >
            Reset
          </button>
        </div>
        {modelOptions.length ? (
          <>
            <div style={{ marginTop: 12, fontWeight: 600 }}>Switch llama.cpp model</div>
            <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8, marginTop: 6 }}>
              <label>Model</label>
              <select
                value={selectedModelKey}
                disabled={isStreaming}
                onChange={(e) => {
                  setSelectedModelKey(e.target.value);
                  setModelSwitchConfirmed(false);
                }}
              >
                {modelOptions.map((opt) => (
                  <option key={opt.key} value={opt.key}>
                    {opt.display || opt.key}
                  </option>
                ))}
              </select>
            </div>
            {modelOptions.find((opt) => opt.key === selectedModelKey)?.notes ? (
              <div style={{ marginTop: 6, opacity: 0.8 }}>
                {modelOptions.find((opt) => opt.key === selectedModelKey)?.notes}
              </div>
            ) : null}
            <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
              <input
                type="checkbox"
                checked={modelSwitchConfirmed}
                onChange={(e) => setModelSwitchConfirmed(e.target.checked)}
              />
              I confirm I want to switch the llama.cpp model (server will restart).
            </label>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button type="button" onClick={switchModel} disabled={isStreaming || !selectedModelKey}>
                Switch model
              </button>
            </div>
          </>
        ) : null}
        <div style={{ marginTop: 8, opacity: 0.7 }}>
          Switches the backend to a different llama.cpp server URL. Use the switcher below to restart llama.cpp.
        </div>
        {modelError ? <div style={{ marginTop: 8, color: "#b00" }}>{modelError}</div> : null}
      </div>

      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 6, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Operations</div>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
          <div>Backend</div>
          <div>{serviceStatus?.backend ?? "unknown"}</div>
          <div>llama.cpp</div>
          <div>
            {serviceStatus?.llama?.running ? "running" : "stopped"}{" "}
            <span style={{ opacity: 0.7 }}>({serviceStatus?.llama?.url ?? "n/a"})</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button type="button" onClick={refreshStatus} disabled={isStreaming}>
            Refresh status
          </button>
          <button type="button" onClick={loadLogs} disabled={isStreaming}>
            Load logs
          </button>
          <button type="button" onClick={loadEvents} disabled={isStreaming}>
            Load events
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8, marginTop: 8 }}>
          <label>Log level</label>
          <select value={logLevel} onChange={(e) => setLogLevel(e.target.value)}>
            <option value="">(all)</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <label>Log contains</label>
          <input
            value={logContains}
            onChange={(e) => setLogContains(e.target.value)}
            placeholder="filter text"
          />
          <label>Event type</label>
          <input
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            placeholder="e.g., llm_request"
          />
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <input
            type="checkbox"
            checked={llamaActionConfirm}
            onChange={(e) => setLlamaActionConfirm(e.target.checked)}
          />
          I confirm I want to start/stop llama.cpp.
        </label>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button type="button" onClick={startLlama} disabled={isStreaming}>
            Start llama.cpp
          </button>
          <button type="button" onClick={stopLlama} disabled={isStreaming}>
            Stop llama.cpp
          </button>
        </div>
        {serviceError ? <div style={{ marginTop: 8, color: "#b00" }}>{serviceError}</div> : null}
        {logData ? (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Recent logs</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <pre
                style={{
                  padding: 8,
                  border: "1px solid #ddd",
                  borderRadius: 6,
                  background: "#fafafa",
                  maxHeight: 200,
                  overflowY: "auto",
                  whiteSpace: "pre-wrap",
                }}
              >
                {(logData.app_log ?? []).join("\n") || "No app logs."}
              </pre>
              <pre
                style={{
                  padding: 8,
                  border: "1px solid #ddd",
                  borderRadius: 6,
                  background: "#fafafa",
                  maxHeight: 200,
                  overflowY: "auto",
                  whiteSpace: "pre-wrap",
                }}
              >
                {(logData.error_log ?? []).join("\n") || "No error logs."}
              </pre>
            </div>
          </div>
        ) : null}
        {eventsData.length ? (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Recent events</div>
            <pre
              style={{
                padding: 8,
                border: "1px solid #ddd",
                borderRadius: 6,
                background: "#fafafa",
                maxHeight: 220,
                overflowY: "auto",
                whiteSpace: "pre-wrap",
              }}
            >
              {eventsData
                .map(
                  (evt) =>
                    `#${evt.id} ${evt.type} conv=${evt.conversation_id ?? "n/a"} msg=${evt.causality_message_id ?? "n/a"}\n${evt.payload_json}`,
                )
                .join("\n\n")}
            </pre>
          </div>
        ) : null}
      </div>

      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 6, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Tools</div>
        {tools.length ? (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8, alignItems: "center" }}>
              <label>Tool</label>
              <select
                value={selectedToolId}
                disabled={isStreaming}
                onChange={(e) => {
                  setSelectedToolId(e.target.value);
                  setToolConfirmed(false);
                  setToolError(null);
                  setToolRunResult(null);
                }}
              >
                {tools.map((tool) => (
                  <option key={tool.tool_id} value={tool.tool_id}>
                    {tool.tool_id}
                  </option>
                ))}
              </select>
              <label>Causality message</label>
              <select
                value={toolCausalityMessageId}
                disabled={isStreaming}
                onChange={(e) =>
                  setToolCausalityMessageId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">Select user message...</option>
                {messages
                  .filter((m) => m.role === "user" && m.id != null)
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id}: {m.content.slice(0, 48)}
                    </option>
                  ))}
              </select>
              <label>Tool input (JSON)</label>
              <textarea
                value={toolInput}
                disabled={isStreaming}
                onChange={(e) => setToolInput(e.target.value)}
                rows={5}
                style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}
              />
            </div>

            <div style={{ marginTop: 10, padding: 10, border: "1px solid #eee", borderRadius: 6 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Quick inputs</div>
              {selectedToolId === "list_dir" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Path</label>
                  <input value={toolForm.path} onChange={(e) => setToolForm({ ...toolForm, path: e.target.value })} />
                  <label>Recursive</label>
                  <input
                    type="checkbox"
                    checked={toolForm.recursive}
                    onChange={(e) => setToolForm({ ...toolForm, recursive: e.target.checked })}
                  />
                  <label>Max entries</label>
                  <input
                    value={toolForm.max_entries}
                    onChange={(e) => setToolForm({ ...toolForm, max_entries: e.target.value })}
                  />
                </div>
              ) : null}

              {selectedToolId === "read_file" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Path</label>
                  <input value={toolForm.path} onChange={(e) => setToolForm({ ...toolForm, path: e.target.value })} />
                  <label>Max bytes</label>
                  <input
                    value={toolForm.max_bytes}
                    onChange={(e) => setToolForm({ ...toolForm, max_bytes: e.target.value })}
                  />
                </div>
              ) : null}

              {selectedToolId === "search_text" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Pattern</label>
                  <input
                    value={toolForm.pattern}
                    onChange={(e) => setToolForm({ ...toolForm, pattern: e.target.value })}
                  />
                  <label>Path</label>
                  <input value={toolForm.path} onChange={(e) => setToolForm({ ...toolForm, path: e.target.value })} />
                  <label>Max matches</label>
                  <input
                    value={toolForm.max_matches}
                    onChange={(e) => setToolForm({ ...toolForm, max_matches: e.target.value })}
                  />
                </div>
              ) : null}

              {selectedToolId === "stat_path" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Path</label>
                  <input value={toolForm.path} onChange={(e) => setToolForm({ ...toolForm, path: e.target.value })} />
                </div>
              ) : null}

              {selectedToolId === "write_file" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Path</label>
                  <input value={toolForm.path} onChange={(e) => setToolForm({ ...toolForm, path: e.target.value })} />
                  <label>Mode</label>
                  <select
                    value={toolForm.mode}
                    onChange={(e) => setToolForm({ ...toolForm, mode: e.target.value as "overwrite" | "append" })}
                  >
                    <option value="overwrite">overwrite</option>
                    <option value="append">append</option>
                  </select>
                  <label>Content</label>
                  <textarea
                    rows={4}
                    value={toolForm.content}
                    onChange={(e) => setToolForm({ ...toolForm, content: e.target.value })}
                  />
                </div>
              ) : null}

              {selectedToolId === "git_diff" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Staged</label>
                  <input
                    type="checkbox"
                    checked={toolForm.staged}
                    onChange={(e) => setToolForm({ ...toolForm, staged: e.target.checked })}
                  />
                  <label>Path</label>
                  <input value={toolForm.path} onChange={(e) => setToolForm({ ...toolForm, path: e.target.value })} />
                </div>
              ) : null}

              {selectedToolId === "git_show" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Ref</label>
                  <input value={toolForm.ref} onChange={(e) => setToolForm({ ...toolForm, ref: e.target.value })} />
                </div>
              ) : null}

              {selectedToolId === "sql_query" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Query</label>
                  <textarea
                    rows={4}
                    value={toolForm.query}
                    onChange={(e) => setToolForm({ ...toolForm, query: e.target.value })}
                  />
                  <label>Max rows</label>
                  <input
                    value={toolForm.max_rows}
                    onChange={(e) => setToolForm({ ...toolForm, max_rows: e.target.value })}
                  />
                </div>
              ) : null}

              {selectedToolId === "open_url" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>URL</label>
                  <input value={toolForm.url} onChange={(e) => setToolForm({ ...toolForm, url: e.target.value })} />
                </div>
              ) : null}

              {selectedToolId === "run_command" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Command</label>
                  <input
                    value={toolForm.command}
                    onChange={(e) => setToolForm({ ...toolForm, command: e.target.value })}
                  />
                  <label>Args (comma separated)</label>
                  <input value={toolForm.args} onChange={(e) => setToolForm({ ...toolForm, args: e.target.value })} />
                </div>
              ) : null}

              {selectedToolId === "apply_patch" ? (
                <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: 8 }}>
                  <label>Patch</label>
                  <textarea
                    rows={6}
                    value={toolForm.patch}
                    onChange={(e) => setToolForm({ ...toolForm, patch: e.target.value })}
                  />
                </div>
              ) : null}

              <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                <button type="button" onClick={applyToolForm} disabled={isStreaming}>
                  Apply to JSON
                </button>
              </div>
            </div>

            {tools.find((tool) => tool.tool_id === selectedToolId)?.requires_confirmation ? (
              <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                <input
                  type="checkbox"
                  checked={toolConfirmed}
                  onChange={(e) => setToolConfirmed(e.target.checked)}
                />
                I confirm I want to run this tool.
              </label>
            ) : null}

            {tools.find((tool) => tool.tool_id === selectedToolId)?.requires_network ? (
              <div style={{ marginTop: 8, color: "#a33" }}>
                This tool requires network access and is disabled unless explicitly enabled.
              </div>
            ) : null}

            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button
                type="button"
                onClick={runTool}
                disabled={
                  isStreaming ||
                  !selectedToolId ||
                  !toolCausalityMessageId ||
                  (tools.find((tool) => tool.tool_id === selectedToolId)?.requires_confirmation &&
                    !toolConfirmed)
                }
              >
                Run tool
              </button>
              <button
                type="button"
                onClick={() => {
                  setToolRunResult(null);
                  setToolError(null);
                }}
                disabled={isStreaming}
              >
                Clear
              </button>
            </div>
            {toolError ? (
              <div style={{ marginTop: 8, color: "#b00" }}>{toolError}</div>
            ) : null}
            {toolRunResult ? (
              <pre
                style={{
                  marginTop: 8,
                  padding: 8,
                  border: "1px solid #ddd",
                  borderRadius: 6,
                  background: "#fafafa",
                  whiteSpace: "pre-wrap",
                }}
              >
                {JSON.stringify(toolRunResult, null, 2)}
              </pre>
            ) : null}
          </>
        ) : (
          <div style={{ opacity: 0.7 }}>No tools available.</div>
        )}
      </div>

      <form onSubmit={send} style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isStreaming ? "Streaming..." : "Type a message"}
          disabled={isStreaming}
          style={{ flex: 1, padding: 10 }}
        />
        <button type="submit" disabled={!canSend} style={{ padding: "10px 14px" }}>
          Send
        </button>
      </form>
    </div>
  );
}
