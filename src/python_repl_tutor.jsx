import React, { useState, useRef, useEffect } from "react";

const COLORS = {
  bg: "#12181F",
  panel: "#161E27",
  panelEdge: "#232D39",
  text: "#E7E5DC",
  muted: "#7C8896",
  blue: "#4F8FC0",
  amber: "#E3A542",
  codeBg: "#0D1218",
  error: "#C4715A",
};

const LEVELS = ["Beginner", "Intermediate", "Advanced"];

// ── OpenRouter (single provider) ─────────────────────────────────────
// The key lives server-side: Vite proxies /api/openrouter during development
// and server.py proxies it in production. The browser only receives the model
// id from /api/config.
const CHAT_URL = "/api/openrouter/chat/completions";
const FALLBACK_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free";

const STARTERS = {
  Beginner: [
    "What's the difference between a list and a tuple?",
    "Explain for-loops with a simple example",
    "Why do I need to indent my code?",
  ],
  Intermediate: [
    "How do list comprehensions actually work?",
    "Debug my BeautifulSoup scraper's rate limiting",
    "When should I use a class vs. a plain function?",
  ],
  Advanced: [
    "Walk me through Python's GIL and threading",
    "How do generators and yield actually work under the hood?",
    "Best practices for structuring a data pipeline package",
  ],
};

function buildSystemPrompt(level) {
  const base =
    "You are a patient, precise Python tutor running inside an interactive REPL-style teaching console. " +
    "Teach by explaining the 'why', not just the 'how'. Always include a short, runnable code example when a concept " +
    "benefits from one, formatted in a fenced code block with the python language tag. Ask a small follow-up question " +
    "or suggest a next step at the end of your answer to keep the lesson moving. Keep answers focused — " +
    "prefer one clear example over several. When the learner shares code with an error, diagnose it directly before " +
    "explaining the underlying concept.";
  const levelNotes = {
    Beginner:
      "The learner is new to Python. Avoid jargon unless you define it immediately. Use everyday analogies. " +
      "Keep code examples under 8 lines.",
    Intermediate:
      "The learner is comfortable with core syntax (loops, functions, basic data structures) and has built small " +
      "real projects, including a BeautifulSoup-based web scraper. Skip basic definitions. Favor practical, " +
      "slightly-real-world examples (automation, working with APIs/data) over toy examples. It's fine to introduce " +
      "idiomatic patterns (comprehensions, context managers, decorators) when relevant.",
    Advanced:
      "The learner wants depth: internals, performance trade-offs, and idiomatic/production-grade patterns. " +
      "Don't oversimplify. Reference relevant standard-library or ecosystem tools by name.",
  };
  return `${base}\n\n${levelNotes[level]}`;
}

function parseContent(text) {
  const parts = [];
  const regex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    parts.push({ type: "code", value: match[2].replace(/\n$/, "") });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push({ type: "text", value: text.slice(lastIndex) });
  }
  return parts;
}

function MessageBlock({ role, content }) {
  const isUser = role === "user";
  const parts = parseContent(content);
  return (
    <div style={{ marginBottom: 22, display: "flex", gap: 10 }}>
      <div
        style={{
          fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
          fontSize: 13,
          color: isUser ? COLORS.amber : COLORS.blue,
          flexShrink: 0,
          paddingTop: 2,
          userSelect: "none",
        }}
      >
        {isUser ? ">>>" : "..."}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {parts.map((p, i) =>
          p.type === "code" ? (
            <pre
              key={i}
              style={{
                background: COLORS.codeBg,
                border: `1px solid ${COLORS.panelEdge}`,
                borderLeft: `3px solid ${COLORS.blue}`,
                borderRadius: 3,
                padding: "10px 14px",
                overflowX: "auto",
                margin: "8px 0",
                fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
                fontSize: 13,
                lineHeight: 1.55,
                color: "#D6E4EF",
              }}
            >
              {p.value}
            </pre>
          ) : (
            p.value.trim() && (
              <p
                key={i}
                style={{
                  margin: "0 0 4px 0",
                  fontSize: 14.5,
                  lineHeight: 1.6,
                  color: isUser ? COLORS.text : "#D9D6CB",
                  whiteSpace: "pre-wrap",
                }}
              >
                {p.value.trim()}
              </p>
            )
          )
        )}
      </div>
    </div>
  );
}

export default function PythonTutorConsole() {
  const [level, setLevel] = useState("Intermediate");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const scrollRef = useRef(null);
  const [model, setModel] = useState(FALLBACK_MODEL);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    fetch("/api/config")
      .then((response) => (response.ok ? response.json() : null))
      .then((config) => {
        if (config?.model) setModel(config.model);
      })
      .catch(() => {
        // Keep the baked fallback; the request itself will surface any error.
      });
  }, []);

  async function streamChat(modelId, messages, onToken) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(CHAT_URL, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: modelId,
          max_tokens: 2000,
          stream: true,
          messages,
        }),
      });
      if (!response.ok) {
        const body = await response.text().catch(() => "");
        throw new Error(`${response.status} ${body.slice(0, 160)}`);
      }
      if (!response.body) throw new Error("no stream");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const payload = trimmed.slice(5).trim();
          if (!payload || payload === "[DONE]") continue;
          let chunk;
          try {
            chunk = JSON.parse(payload);
          } catch {
            continue;
          }
          const delta = chunk.choices?.[0]?.delta?.content;
          if (delta) onToken(delta);
        }
      }
    } finally {
      clearTimeout(timeout);
    }
  }

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setErrorMsg(null);
    const nextMessages = [...messages, { role: "user", content: trimmed }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);

    const chatMessages = [
      { role: "system", content: buildSystemPrompt(level) },
      ...nextMessages.map((m) => ({ role: m.role, content: m.content })),
    ];

    let assistantText = "";
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    try {
      await streamChat(model, chatMessages, (token) => {
        assistantText += token;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: assistantText };
          return next;
        });
      });
      if (!assistantText.trim()) throw new Error("empty response");
      setLoading(false);
    } catch (err) {
      setMessages((prev) => prev.slice(0, -1));
      const detail =
        err.name === "AbortError"
          ? "timed out"
          : `${err.message}`.split("\n")[0].slice(0, 120);
      setErrorMsg(`Tutor request failed (${detail}). Check the server logs and try again.`);
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "640px",
        maxWidth: 760,
        margin: "0 auto",
        background: COLORS.bg,
        border: `1px solid ${COLORS.panelEdge}`,
        borderRadius: 6,
        overflow: "hidden",
        fontFamily: "Georgia, 'Iowan Old Style', serif",
      }}
    >
      {/* header */}
      <div
        style={{
          padding: "14px 20px",
          borderBottom: `1px solid ${COLORS.panelEdge}`,
          background: COLORS.panel,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ fontSize: 16, color: COLORS.text, letterSpacing: 0.2 }}>
            Python, interactively
          </div>
          <div
            style={{
              fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
              fontSize: 11.5,
              color: COLORS.muted,
              marginTop: 2,
            }}
          >
            Python 3.x console — a tutor sits behind the prompt
          </div>
        </div>
        <div style={{ display: "flex", gap: 2 }}>
          {LEVELS.map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevel(lvl)}
              style={{
                fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
                fontSize: 11.5,
                padding: "5px 10px",
                background: level === lvl ? COLORS.blue : "transparent",
                color: level === lvl ? "#0D1218" : COLORS.muted,
                border: `1px solid ${level === lvl ? COLORS.blue : COLORS.panelEdge}`,
                borderRadius: 3,
                cursor: "pointer",
              }}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {/* transcript */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "20px 22px" }}>
        {messages.length === 0 && (
          <div>
            <p style={{ color: COLORS.muted, fontSize: 14, lineHeight: 1.6, marginBottom: 16 }}>
              Ask anything — a concept, an error message, or code you want reviewed. Pick a level
              above to set how much is explained. A few ways to start:
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {STARTERS[level].map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  style={{
                    textAlign: "left",
                    background: COLORS.panel,
                    border: `1px solid ${COLORS.panelEdge}`,
                    borderLeft: `3px solid ${COLORS.amber}`,
                    borderRadius: 3,
                    padding: "9px 12px",
                    color: "#D9D6CB",
                    fontFamily: "Georgia, serif",
                    fontSize: 13.5,
                    cursor: "pointer",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBlock key={i} role={m.role} content={m.content} />
        ))}

        {loading && (
          <div style={{ display: "flex", gap: 10 }}>
            <div
              style={{
                fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
                fontSize: 13,
                color: COLORS.blue,
              }}
            >
              ...
            </div>
            <div style={{ color: COLORS.muted, fontSize: 13.5, fontStyle: "italic" }}>
              thinking
            </div>
          </div>
        )}

        {errorMsg && (
          <div style={{ color: COLORS.error, fontSize: 13, marginTop: 6 }}>{errorMsg}</div>
        )}
      </div>

      {/* input */}
      <div
        style={{
          borderTop: `1px solid ${COLORS.panelEdge}`,
          background: COLORS.panel,
          padding: 12,
          display: "flex",
          gap: 8,
          alignItems: "flex-end",
        }}
      >
        <div
          style={{
            fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
            color: COLORS.amber,
            fontSize: 13,
            paddingBottom: 9,
          }}
        >
          &gt;&gt;&gt;
        </div>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a question and press Enter..."
          rows={1}
          style={{
            flex: 1,
            resize: "none",
            background: COLORS.codeBg,
            border: `1px solid ${COLORS.panelEdge}`,
            borderRadius: 3,
            color: COLORS.text,
            fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
            fontSize: 13.5,
            padding: "8px 10px",
            outline: "none",
          }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          style={{
            background: loading || !input.trim() ? COLORS.panelEdge : COLORS.blue,
            color: loading || !input.trim() ? COLORS.muted : "#0D1218",
            border: "none",
            borderRadius: 3,
            padding: "9px 16px",
            fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
            fontSize: 13,
            cursor: loading || !input.trim() ? "default" : "pointer",
          }}
        >
          Run
        </button>
      </div>
    </div>
  );
}
