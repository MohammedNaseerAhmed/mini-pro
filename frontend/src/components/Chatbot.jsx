import { useCallback, useEffect, useRef, useState, useMemo } from "react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

/* ── Constants ───────────────────────────────────────────────────────────── */
const LANG_OPTIONS = [
  { code:"en",label:"English" }, { code:"hi",label:"हिन्दी" },
  { code:"te",label:"తెలుగు" },  { code:"kn",label:"ಕನ್ನಡ" },
  { code:"ta",label:"தமிழ்" },   { code:"ml",label:"മലയാളം" },
  { code:"mr",label:"मराठी" },   { code:"simple_en",label:"Plain English" },
];
const MODE_OPTIONS = [
  { code:"auto",    icon:"◈", label:"Auto",     color:"text-gold-400"   },
  { code:"hybrid",  icon:"⚡", label:"Hybrid",   color:"text-amber-400"  },
  { code:"rag",     icon:"📁", label:"Document", color:"text-blue-400"   },
  { code:"general", icon:"⚖", label:"Law",      color:"text-emerald-400"},
];
const QUICK = [
  "Who is the petitioner?","What sections apply?",
  "Summarise key facts","Bail eligibility?",
  "Explain the outcome","FIR validity?",
];
const INIT_MSG = {
  role:"bot", id:0,
  text:"Welcome. I am **Lex**, your AI legal counsel.\n\nI can:\n• Analyse the **uploaded document** in depth\n• Explain **Indian law** — IPC, BNS, CrPC, BNSS\n• Apply law to your case in **Hybrid mode**\n\nSelect a mode and ask your first question.",
  mode:null, confidence:null,
};

/* ── Markdown renderer ───────────────────────────────────────────────────── */
function renderMd(text) {
  if (!text) return null;
  const lines = text.split("\n");
  const out = [];
  let buf = [];
  const flush = () => {
    if (!buf.length) return;
    out.push(
      <ul key={`ul${out.length}`} className="my-2 space-y-1 pl-4">
        {buf.map((li, i) => <li key={i} className="text-sm leading-relaxed text-slate-300">{inline(li)}</li>)}
      </ul>
    );
    buf = [];
  };
  lines.forEach((ln, i) => {
    const b = ln.match(/^[•\-*]\s+(.+)/);
    if (b) { buf.push(b[1]); return; }
    flush();
    if (!ln.trim()) { out.push(<br key={`br${i}`} />); return; }
    if (/^#{1,3}\s/.test(ln)) {
      out.push(<p key={`h${i}`} className="font-semibold text-gold-300 mt-3 mb-1 text-sm tracking-wide" style={{fontFamily:"'Cormorant Garamond',serif"}}>{ln.replace(/^#+\s/,"")}</p>);
      return;
    }
    out.push(<span key={`l${i}`} className="block text-sm leading-relaxed text-slate-300">{inline(ln)}</span>);
  });
  flush();
  return out;
}
function inline(t) {
  return t.split(/(\*\*[^*]+\*\*)/g).map((p,i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i} className="text-gold-200 font-semibold">{p.slice(2,-2)}</strong>
      : p
  );
}

/* ── Copy Button ─────────────────────────────────────────────────────────── */
function CopyBtn({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setOk(true); setTimeout(()=>setOk(false),1800); }}
      className="opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 rounded text-[9px] font-bold uppercase tracking-widest border border-white/10 hover:border-gold-400/40 text-slate-500 hover:text-gold-400"
    >{ok ? "✓ Copied" : "Copy"}</button>
  );
}

/* ── Confidence badge ────────────────────────────────────────────────────── */
function ConfBadge({ score }) {
  if (!score) return null;
  const pct = Math.round(score * 100);
  const col = pct>=85 ? "text-emerald-400 border-emerald-400/25 bg-emerald-400/08"
            : pct>=65 ? "text-gold-400 border-gold-400/25 bg-gold-400/08"
            :           "text-rose-400 border-rose-400/25 bg-rose-400/08";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[9px] font-black uppercase tracking-widest ${col}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {pct}% confidence
    </span>
  );
}

/* ── Skeleton loader ─────────────────────────────────────────────────────── */
function Skeleton() {
  return (
    <div className="flex gap-4 max-w-[88%] animate-fade-up">
      <div className="w-8 h-8 rounded-full bg-navy-700 border border-gold-400/20 flex items-center justify-center text-gold-400 text-sm shrink-0 mt-1">⚖</div>
      <div className="flex-1 space-y-2 pt-1">
        <div className="text-[9px] font-black tracking-widest text-gold-400/60 uppercase mb-3">⚖ Lex AI — Analysing…</div>
        <div className="shimmer h-3 rounded-full w-3/4" />
        <div className="shimmer h-3 rounded-full w-full" />
        <div className="shimmer h-3 rounded-full w-2/3" />
        <div className="shimmer h-3 rounded-full w-5/6 mt-1" />
      </div>
    </div>
  );
}

/* ── Bot bubble ──────────────────────────────────────────────────────────── */
function BotBubble({ msg, idx }) {
  const modeColor = {
    rag_content:"text-blue-400", legal_knowledge:"text-emerald-400",
    hybrid:"text-amber-400", metadata:"text-purple-400",
  };
  return (
    <div className="flex gap-4 max-w-[88%] group animate-fade-up" style={{animationDelay:`${idx*30}ms`}}>
      <div className="w-8 h-8 rounded-full shrink-0 mt-1 border border-gold-400/30 bg-navy-800 flex items-center justify-center text-gold-400 text-sm shadow-gold">
        ⚖
      </div>
      <div className="flex-1 min-w-0 space-y-2">
        <div className="text-[9px] font-black tracking-[0.18em] uppercase text-gold-400/70 flex items-center gap-2">
          <span className="gold-line-in block w-6 h-px bg-gold-400" />
          ⚖ Lex AI
          {msg.mode && <span className={`${modeColor[msg.mode]||"text-slate-500"}`}>· {msg.mode.replace(/_/g," ")}</span>}
        </div>
        <div className="glass-card rounded-2xl rounded-tl-sm p-5 lex-border">
          <div className="space-y-1">{renderMd(msg.text)}</div>
        </div>
        <div className="flex items-center gap-3 px-1">
          <ConfBadge score={msg.confidence} />
          <span className="text-[10px] text-slate-600 font-mono tabular-nums">{msg.time}</span>
          <CopyBtn text={msg.text} />
          <button className="opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 rounded text-[9px] font-bold uppercase tracking-widest border border-white/10 hover:border-gold-400/40 text-slate-500 hover:text-gold-400">
            🔖
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── User bubble ─────────────────────────────────────────────────────────── */
function UserBubble({ msg }) {
  return (
    <div className="flex flex-row-reverse gap-4 max-w-[80%] self-end animate-fade-up">
      <div className="w-8 h-8 rounded-full shrink-0 mt-1 bg-navy-600 border border-white/10 flex items-center justify-center text-slate-400 text-xs">
        👤
      </div>
      <div className="flex flex-col items-end gap-1.5">
        <div className="bg-navy-600 border border-white/10 rounded-2xl rounded-tr-sm px-5 py-3.5 text-sm text-slate-200 leading-relaxed shadow-soft">
          {msg.text}
        </div>
        <span className="text-[10px] text-slate-600 font-mono px-1">{msg.time}</span>
      </div>
    </div>
  );
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
function EmptyState({ onQuick }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center relative">
      <div className="scales-watermark">
        <svg viewBox="0 0 100 100" className="w-64 h-64 fill-current text-white">
          <path d="M50 5 L52 15 L75 15 C77 15 78 17 77 19 L65 42 C63 46 57 48 53 46 L52 45 L52 55 L62 55 C64 55 66 57 66 59 L66 65 L34 65 L34 59 C34 57 36 55 38 55 L48 55 L48 45 L47 46 C43 48 37 46 35 42 L23 19 C22 17 23 15 25 15 L48 15 L50 5 Z M35 19 L45 40 L35 19 Z M65 19 L55 40 L65 19 Z"/>
        </svg>
      </div>
      <div className="animate-float mb-8 text-5xl">⚖</div>
      <h3 className="legal-heading text-3xl mb-3">Counsel Awaits</h3>
      <p className="text-slate-500 text-sm leading-relaxed max-w-sm mb-8 italic" style={{fontFamily:"'Cormorant Garamond',serif",fontSize:"17px"}}>
        "Justice delayed is justice denied."
        <span className="block text-xs mt-1 not-italic tracking-widest uppercase text-slate-600">— Gladstone</span>
      </p>
      <div className="flex flex-wrap gap-2 justify-center max-w-sm">
        {QUICK.map((q,i) => (
          <button key={i} onClick={() => onQuick(q)}
            className="px-3 py-1.5 rounded-full text-[11px] font-medium border border-gold-400/20 text-gold-300/70 hover:border-gold-400/50 hover:text-gold-300 transition-all hover:bg-gold-400/05">
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Status Bar ──────────────────────────────────────────────────────────── */
function StatusBar({ asking, msgCount, mode }) {
  return (
    <div className="flex items-center gap-4 px-5 py-2 border-t border-white/05 bg-navy-950/60 text-[10px] font-mono text-slate-600">
      <div className="flex items-center gap-1.5">
        <div className="status-dot" />
        <span>Connected</span>
      </div>
      <span className="text-navy-500">|</span>
      <span>Model: Groq / llama-3.3-70b</span>
      <span className="text-navy-500">|</span>
      <span>Mode: {mode.toUpperCase()}</span>
      <span className="text-navy-500">|</span>
      <span>{msgCount} messages</span>
      {asking && <><span className="text-navy-500">|</span><span className="text-gold-400 animate-pulse">● Processing…</span></>}
    </div>
  );
}

/* ── Main Component ──────────────────────────────────────────────────────── */
export default function Chatbot({ api: apiProp, caseNumber="", language="en", setLanguage=()=>{} }) {
  const [open, setOpen]       = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState([INIT_MSG]);
  const [input, setInput]     = useState("");
  const [asking, setAsking]   = useState(false);
  const [mode, setMode]       = useState("auto");
  const bottomRef = useRef(null);
  const taRef     = useRef(null);
  const msgId     = useRef(1);

  const fmt = () => new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
  const addMsg = (m) => setMessages(p => [...p, {...m, id: msgId.current++}]);

  const adjustTA = useCallback(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 130) + "px";
  }, []);

  useEffect(() => { adjustTA(); }, [input, adjustTA]);
  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({behavior:"smooth"});
  }, [messages, open, expanded]);

  const history = useMemo(() =>
    messages.filter(m => m.role==="user"||m.role==="bot").map(m=>({
      role: m.role==="user"?"user":"assistant", text: m.text,
    })), [messages]);

  const send = useCallback(async (q) => {
    const text = (q || input).trim();
    if (!text || asking) return;
    setInput("");
    addMsg({ role:"user", text, time:fmt() });
    setAsking(true);
    try {
      const fn = apiProp || ((path, opts) => fetch(`${API}${path}`, opts||{}).then(r=>r.json()));
      const data = await fn("/chatbot/ask", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          query:text, case_number:caseNumber||undefined,
          language, response_mode:mode, chat_history:history,
        }),
      });
      addMsg({
        role:"bot",
        text: data.answer || "I could not retrieve an answer.",
        mode: data.mode, confidence: data.confidence||null, time:fmt(),
      });
    } catch(e) {
      addMsg({ role:"bot", text:`**Error:** ${e.message}`, time:fmt() });
    } finally { setAsking(false); }
  }, [input, asking, apiProp, caseNumber, language, mode, history]);

  const onKey = (e) => { if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); send(); } };
  const clear = () => setMessages([{ ...INIT_MSG, id: msgId.current++ }]);

  const userMsgs = messages.filter(m => m.role==="user").length;
  const showEmpty = userMsgs === 0;

  return (
    <>
      {/* FAB */}
      <button
        id="chat-fab"
        onClick={() => setOpen(v=>!v)}
        className={`fixed bottom-8 right-8 z-[100] w-16 h-16 rounded-full flex items-center justify-center text-2xl transition-all duration-300 group
          ${open
            ? "bg-navy-700 border border-gold-400/30 text-gold-400 rotate-45"
            : "bg-gold-400 text-navy-900 shadow-gold hover:scale-110 active:scale-95"
          }`}
      >
        <span className="relative z-10 font-bold">{open ? "✕" : "⚖"}</span>
        {!open && <span className="absolute inset-0 rounded-full border-2 border-gold-400/40 animate-ping pointer-events-none" />}
      </button>

      {/* Chat panel */}
      {open && (
        <div
          role="dialog"
          aria-label="Lex AI Legal Assistant"
          className={`fixed bottom-28 right-8 z-[99] flex flex-col overflow-hidden
            border border-gold-400/18 rounded-2xl shadow-glass
            animate-in zoom-in-95 slide-in-from-bottom-8 duration-300
            transition-all`}
          style={{
            background:"rgba(10,14,26,0.96)",
            backdropFilter:"blur(24px)",
            width: expanded ? "min(960px,calc(100vw - 64px))" : "min(460px,calc(100vw - 32px))",
            height: expanded ? "calc(100vh - 148px)" : "min(680px,calc(100vh - 148px))",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/06 shrink-0"
            style={{background:"rgba(5,8,15,0.6)"}}>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gold-400/10 border border-gold-400/30 flex items-center justify-center text-gold-400 text-base shadow-gold">⚖</div>
              <div>
                <div className="text-sm font-semibold text-gold-200 tracking-wider" style={{fontFamily:"'Cormorant Garamond',serif",fontSize:"16px"}}>Lex AI Counsel</div>
                <div className="text-[9px] font-bold tracking-[0.18em] uppercase text-slate-600">
                  {caseNumber ? `📋 ${caseNumber}` : "General Legal Intelligence"}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={() => setExpanded(v=>!v)}
                className="w-8 h-8 rounded-lg hover:bg-white/05 text-slate-500 hover:text-gold-400 flex items-center justify-center text-xs transition-colors"
                title={expanded?"Collapse":"Expand"}>
                {expanded ? "⊡" : "⊞"}
              </button>
              <button onClick={clear}
                className="w-8 h-8 rounded-lg hover:bg-white/05 text-slate-500 hover:text-rose-400 flex items-center justify-center text-sm transition-colors" title="Clear">
                🗑
              </button>
              <button onClick={() => setOpen(false)}
                className="w-8 h-8 rounded-lg hover:bg-white/05 text-slate-500 hover:text-slate-300 flex items-center justify-center text-sm transition-colors">
                ✕
              </button>
            </div>
          </div>

          {/* Mode + Lang bar */}
          <div className="px-5 py-3 border-b border-white/04 shrink-0 flex items-center gap-4 flex-wrap"
            style={{background:"rgba(5,8,15,0.35)"}}>
            <div className="flex items-center gap-2">
              <span className="label-xs">Mode</span>
              <div className="flex gap-1">
                {MODE_OPTIONS.map(m => (
                  <button key={m.code} onClick={() => setMode(m.code)}
                    className={`px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wide transition-all border
                      ${mode===m.code
                        ? "border-gold-400/35 bg-gold-400/10 text-gold-300"
                        : "border-transparent text-slate-600 hover:text-slate-400 hover:border-white/08"
                      }`}>
                    {m.icon} {m.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <span className="label-xs">Lang</span>
              <select value={language} onChange={e=>setLanguage(e.target.value)}
                className="gold-select"
                style={{ fontSize: "11px", padding: "0.35rem 2rem 0.35rem 0.6rem", width: "auto" }}>
                {LANG_OPTIONS.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6 relative">
            {showEmpty
              ? <EmptyState onQuick={send} />
              : messages.map((m, i) =>
                  m.role==="bot"
                    ? <BotBubble key={m.id} msg={m} idx={i} />
                    : <UserBubble key={m.id} msg={m} />
                )
            }
            {asking && <Skeleton />}
            <div ref={bottomRef} />
          </div>

          {/* Quick prompts */}
          {!asking && !showEmpty && (
            <div className="flex gap-2 overflow-x-auto no-scrollbar px-5 py-2.5 border-t border-white/04 shrink-0">
              {QUICK.map((q,i) => (
                <button key={i} onClick={() => send(q)}
                  className="whitespace-nowrap px-3 py-1.5 rounded-full text-[10px] font-medium border border-white/08 text-slate-500 hover:border-gold-400/35 hover:text-gold-300 transition-all shrink-0">
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="px-5 pb-4 pt-2 shrink-0">
            <div className="relative flex items-end gap-3 rounded-xl border border-white/10 focus-within:border-gold-400/50 focus-within:shadow-gold px-4 py-3 transition-all"
              style={{background:"rgba(5,8,15,0.7)"}}>
              <textarea
                ref={taRef}
                id="chat-input"
                rows={1}
                disabled={asking}
                value={input}
                onChange={e => { setInput(e.target.value); adjustTA(); }}
                onKeyDown={onKey}
                placeholder="Query Indian legal dataset…"
                className="flex-1 bg-transparent border-none outline-none text-sm text-slate-200 placeholder:text-slate-700 resize-none max-h-32 leading-relaxed py-1"
                style={{fontFamily:"'DM Sans',sans-serif"}}
              />
              <button
                id="chat-send"
                onClick={() => send()}
                disabled={asking || !input.trim()}
                className="w-9 h-9 rounded-lg bg-gold-400 text-navy-900 flex items-center justify-center text-base font-bold disabled:opacity-30 disabled:grayscale transition-all hover:scale-105 active:scale-95 shrink-0 shadow-gold"
              >➤</button>
            </div>
            <div className="text-center mt-2">
              <span className="text-[9px] font-bold tracking-[0.18em] uppercase text-navy-500" style={{fontFamily:"'IBM Plex Mono',monospace"}}>
                Shift+Enter for newline · Enter to send
              </span>
            </div>
          </div>

          {/* Status bar */}
          <StatusBar asking={asking} msgCount={messages.length} mode={mode} />
        </div>
      )}
    </>
  );
}
