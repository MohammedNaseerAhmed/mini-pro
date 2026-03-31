import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const CHAT_LANG_OPTIONS = [
  { code: "en", label: "🇬🇧 English" },
  { code: "hi", label: "🇮🇳 Hindi" },
  { code: "te", label: "🇮🇳 Telugu" },
  { code: "kn", label: "🇮🇳 Kannada" },
  { code: "ta", label: "🇮🇳 Tamil" },
  { code: "ml", label: "🇮🇳 Malayalam" },
  { code: "mr", label: "🇮🇳 Marathi" },
  { code: "ur", label: "🇵🇰 Urdu" },
  { code: "bn", label: "🇧🇩 Bengali" },
  { code: "pa", label: "🇮🇳 Punjabi" },
  { code: "gu", label: "🇮🇳 Gujarati" },
  { code: "simple_en", label: "🔤 Simple English" },
];

const RESPONSE_MODE_OPTIONS = [
  { code: "auto", label: "Auto", icon: "🤖", color: "var(--text-muted)" },
  { code: "hybrid", label: "Hybrid", icon: "⚡", color: "var(--gold)" },
  { code: "rag", label: "Document", icon: "📁", color: "var(--blue)" },
  { code: "general", label: "Law", icon: "⚖️", color: "var(--green)" },
  { code: "metadata", label: "Metadata", icon: "📋", color: "var(--purple)" },
];

const MODE_COLORS = {
  metadata: { bg: "rgba(168,85,247,0.12)", color: "var(--purple)" },
  rag_content: { bg: "rgba(59,130,246,0.12)", color: "var(--blue)" },
  legal_knowledge: { bg: "rgba(34,197,94,0.12)", color: "var(--green)" },
  hybrid: { bg: "rgba(245,166,35,0.14)", color: "var(--gold)" },
};

const QUICK_PROMPTS = [
  "Who is the petitioner?",
  "What is the outcome?",
  "Summarize the key facts",
  "What is bail?",
  "Explain the sections involved",
  "Does FIR apply here?",
];

const INITIAL_BOT_TEXT =
  "Hello! I'm your Legal AI assistant.\n\n" +
  "I can:\n" +
  "• Answer questions about the **uploaded document**\n" +
  "• Explain **Indian law** (IPC, CrPC, bail, FIR, etc.)\n" +
  "• Use **Hybrid mode** to apply law to your case\n\n" +
  "Choose a mode below and start asking!";

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function createBotMessage(text, mode = null, includeInHistory = true) {
  return {
    role: "bot",
    text,
    time: formatTime(new Date()),
    mode,
    includeInHistory,
  };
}

function createUserMessage(text) {
  return {
    role: "user",
    text,
    time: formatTime(new Date()),
    includeInHistory: true,
  };
}

function buildChatHistory(messages) {
  return messages
    .filter((message) => message.includeInHistory !== false)
    .filter((message) => message.role === "user" || message.role === "bot")
    .map((message) => ({
      role: message.role === "user" ? "user" : "assistant",
      text: message.text,
    }));
}

function renderMarkdown(text) {
  if (!text) return null;

  const lines = text.split("\n");
  const elements = [];
  let listItems = [];
  let blockquoteLines = [];

  const flushList = () => {
    if (listItems.length === 0) return;
    elements.push(
      <ul key={`ul-${elements.length}`} className="chat-md-list">
        {listItems.map((item, index) => <li key={index}>{applyInline(item)}</li>)}
      </ul>
    );
    listItems = [];
  };

  const flushBlockquote = () => {
    if (blockquoteLines.length === 0) return;
    elements.push(
      <blockquote key={`bq-${elements.length}`} className="chat-md-blockquote">
        {blockquoteLines.map((line, index) => (
          <span key={index} className="chat-md-line">{applyInline(line)}</span>
        ))}
      </blockquote>
    );
    blockquoteLines = [];
  };

  lines.forEach((line, index) => {
    const bullet = line.match(/^([•\-*]|\d+\.)\s+(.+)/);
    const blockquote = line.match(/^>\s?(.*)/);

    if (bullet) {
      flushBlockquote();
      listItems.push(bullet[2]);
      return;
    }

    if (blockquote) {
      flushList();
      blockquoteLines.push(blockquote[1]);
      return;
    }

    flushList();
    flushBlockquote();

    if (line.trim() === "") {
      if (index > 0) {
        elements.push(<br key={`br-${index}`} />);
      }
      return;
    }

    elements.push(
      <span key={`ln-${index}`} className="chat-md-line">{applyInline(line)}</span>
    );
  });

  flushList();
  flushBlockquote();
  return elements;
}

function applyInline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <button className="chat-copy-btn" onClick={copy} title="Copy to clipboard">
      {copied ? "✓" : "⧉"}
    </button>
  );
}

function BotBubble({ message }) {
  const mc = MODE_COLORS[message.mode] || {};

  return (
    <div className="chat-bubble bot">
      <div className="chat-bubble-avatar">⚖</div>
      <div className="chat-bubble-body">
        <div className="chat-bubble-text">{renderMarkdown(message.text)}</div>
        <div className="chat-bubble-meta">
          {message.mode && message.mode !== "none" && (
            <span
              className="chat-mode-tag"
              style={{ background: mc.bg, color: mc.color }}
            >
              {message.mode.replace(/_/g, " ")}
            </span>
          )}
          <span className="chat-ts">{message.time}</span>
          <CopyButton text={message.text} />
        </div>
      </div>
    </div>
  );
}

function UserBubble({ message }) {
  return (
    <div className="chat-bubble user">
      <div className="chat-bubble-body user-body">
        <div className="chat-bubble-text">{message.text}</div>
        <div className="chat-bubble-meta" style={{ justifyContent: "flex-end" }}>
          <span className="chat-ts">{message.time}</span>
        </div>
      </div>
    </div>
  );
}

export default function Chatbot({
  api,
  caseNumber = "",
  language = "en",
  setLanguage = () => {},
}) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState([createBotMessage(INITIAL_BOT_TEXT, null, false)]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const [responseMode, setResponseMode] = useState("auto");
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  const activeLanguage = language || "en";

  const adjustTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  useEffect(() => {
    adjustTextarea();
  }, [input, adjustTextarea]);

  useEffect(() => {
    if (open && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, open, expanded]);

  useEffect(() => {
    if (!open) {
      setExpanded(false);
    }
  }, [open]);

  const send = useCallback(async (question) => {
    const q = (question || input).trim();
    if (!q || asking) return;

    const nextUserMessage = createUserMessage(q);
    const chatHistory = buildChatHistory(messages);

    setInput("");
    setMessages((prev) => [...prev, nextUserMessage]);
    setAsking(true);

    try {
      const data = await api("/chatbot/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          case_number: caseNumber || undefined,
          language: activeLanguage,
          response_mode: responseMode,
          chat_history: chatHistory,
        }),
      });

      setMessages((prev) => [
        ...prev,
        createBotMessage(
          data.answer || "I could not find an answer for that question.",
          data.mode
        ),
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        createBotMessage(`⚠️ **Error:** ${error.message}`, null, false),
      ]);
    } finally {
      setAsking(false);
    }
  }, [input, asking, api, caseNumber, activeLanguage, responseMode, messages]);

  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  const clearChat = () => {
    setMessages([
      createBotMessage(
        "Chat cleared. Ask me anything about the document or Indian law!",
        null,
        false
      ),
    ]);
  };

  const activeModeDef = useMemo(
    () => RESPONSE_MODE_OPTIONS.find((mode) => mode.code === responseMode) || RESPONSE_MODE_OPTIONS[0],
    [responseMode]
  );

  return (
    <>
      <button
        id="chat-fab"
        className={`chat-fab${open ? " open" : ""}`}
        title="Ask Legal Assistant"
        onClick={() => setOpen((value) => !value)}
        aria-label="Open legal assistant"
      >
        <span className="chat-fab-icon">{open ? "✕" : "⚖"}</span>
        {!open && <span className="chat-fab-pulse" />}
      </button>

      {open && (
        <div
          className={`chat-panel${expanded ? " expanded" : ""}`}
          role="dialog"
          aria-label="Legal Assistant Chat"
        >
          <div className="chat-header">
            <div className="chat-header-left">
              <span className="chat-header-icon">⚖</span>
              <div>
                <div className="chat-header-title">Legal AI Assistant</div>
                <div className="chat-header-sub">
                  {caseNumber
                    ? `📋 Scoped to ${caseNumber}`
                    : "General legal chat · No document scoped"}
                </div>
              </div>
            </div>

            <div className="chat-header-actions">
              <button
                className="chat-action-btn"
                onClick={() => setExpanded((value) => !value)}
                title={expanded ? "Collapse chat" : "Expand chat"}
              >
                {expanded ? "Collapse" : "Expand"}
              </button>
              <button className="chat-icon-btn" onClick={clearChat} title="Clear chat">🗑</button>
              <button className="chat-icon-btn chat-close" onClick={() => setOpen(false)} title="Close">✕</button>
            </div>
          </div>

          <div className="chat-settings-bar">
            <div className="chat-settings-row">
              <span className="chat-settings-label">Language</span>
              <select
                value={activeLanguage}
                onChange={(event) => setLanguage(event.target.value)}
                className="chat-select"
              >
                {CHAT_LANG_OPTIONS.map((option) => (
                  <option key={option.code} value={option.code}>{option.label}</option>
                ))}
              </select>
            </div>

            <div className="chat-settings-row">
              <span className="chat-settings-label">Mode</span>
              <div className="chat-mode-chips">
                {RESPONSE_MODE_OPTIONS.map((mode) => (
                  <button
                    key={mode.code}
                    className={`chat-mode-chip${responseMode === mode.code ? " active" : ""}`}
                    style={responseMode === mode.code ? { borderColor: mode.color, color: mode.color } : {}}
                    onClick={() => setResponseMode(mode.code)}
                    title={`${mode.icon} ${mode.label}`}
                  >
                    {mode.icon} {mode.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="chat-messages">
            {messages.map((message, index) =>
              message.role === "bot"
                ? <BotBubble key={index} message={message} />
                : <UserBubble key={index} message={message} />
            )}

            {asking && (
              <div className="chat-bubble bot">
                <div className="chat-bubble-avatar">⚖</div>
                <div className="chat-bubble-body">
                  <div className="chat-typing">
                    <span /><span /><span />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
                    {activeModeDef.icon} {activeModeDef.label} mode...
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {!asking && (
            <div className="chat-quick-row">
              {QUICK_PROMPTS.map((prompt, index) => (
                <button
                  key={index}
                  className="chat-quick-chip"
                  onClick={() => send(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}

          <div className="chat-input-row">
            <textarea
              id="chat-input"
              ref={textareaRef}
              className="chat-input"
              placeholder="Ask about the document or Indian law... (Enter to send)"
              value={input}
              onChange={(event) => {
                setInput(event.target.value);
                adjustTextarea();
              }}
              onKeyDown={onKeyDown}
              rows={1}
              disabled={asking}
            />
            <button
              id="chat-send"
              className="chat-send"
              onClick={() => send()}
              disabled={asking || !input.trim()}
              title="Send (Enter)"
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </>
  );
}
