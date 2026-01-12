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
      } catch {
        setConversations([]);
        setActiveConversationId(null);
        setMessages([]);
        setPreferences(null);
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
