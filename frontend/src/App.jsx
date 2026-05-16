import { useState, useEffect, useRef, useCallback } from "react";
import "./styles.css";
import UploadZone from "./components/UploadZone";
import RecentCasesPanel from "./components/RecentCasesPanel";
import Chatbot from "./components/Chatbot";
import PredictionPage from "./components/PredictionPage";
import ADRPanel from "./components/ADRPanel";
import { BNSPanel, SectionLookupPage, DraftAnalyzer, DocumentRewriter } from "./components/BNSComponents";
import ECourtsPanel from "./components/eCourtsStatus";
import ECourtsAssistant from "./components/ECourtsAssistant";
import { ManualADRForm } from "./components/ADRPanel";
import IntelligenceDashboard from "./components/IntelligenceDashboard";
import AuthPage from "./components/AuthPage";

// ─── API helper ────────────────────────────────────────────────────────────────
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export async function api(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options || {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
  return data;
}

// ─── Hash Router ──────────────────────────────────────────────────────────────
function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onHash = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash;
}

// ─── Auth State Hook ──────────────────────────────────────────────────────────
function useAuth() {
  const stored = localStorage.getItem("lex_user");
  const [user, setUser] = useState(() => {
    try { return stored ? JSON.parse(stored) : null; } catch { return null; }
  });

  const login = useCallback((userData) => {
    setUser(userData);
    localStorage.setItem("lex_user", JSON.stringify(userData));
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
    } catch (_) {/* best-effort */}
    localStorage.removeItem("lex_token");
    localStorage.removeItem("lex_user");
    setUser(null);
  }, []);

  return { user, login, logout };
}

// ─── Navigation Bar ───────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { href: "#/",             label: "Workspace",    icon: "📤" },
  { href: "#/predict",      label: "Predict",      icon: "🔮" },
  { href: "#/adr",          label: "ADR",          icon: "⚖️" },
  { href: "#/bns",          label: "BNS",          icon: "📖" },
  { href: "#/ecourts",      label: "eCourts",      icon: "🏛️" },
  { href: "#/intelligence", label: "Intelligence", icon: "🧠" },
];

function NavBar({ active, user, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const initials = user?.name
    ? user.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  return (
    <nav className="sticky top-0 z-50 flex flex-col" style={{background:"rgba(5,8,15,0.92)",backdropFilter:"blur(20px)"}}>
      <div className="flex items-center justify-between px-8 py-4">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg border border-gold-400/30 bg-gold-400/10 flex items-center justify-center text-gold-400 text-base shadow-gold">⚖</div>
          <div>
            <span className="text-lg font-semibold text-gold-200 tracking-wide" style={{fontFamily:"'Cormorant Garamond',serif"}}>Lex</span>
            <span className="text-lg text-slate-500" style={{fontFamily:"'Cormorant Garamond',serif"}}>AI</span>
          </div>
        </div>

        {/* Nav links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map(({ href, label, icon }) => {
            const isActive = active === href;
            return (
              <a key={href} href={href}
                className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold tracking-widest uppercase transition-all duration-200 ${
                  isActive
                    ? "text-gold-300 bg-gold-400/08 border border-gold-400/20"
                    : "text-slate-500 hover:text-slate-300 hover:bg-white/04"
                }`}>
                <span className="text-sm">{icon}</span>
                <span>{label}</span>
                {isActive && <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-gold-400 gold-line-in" />}
              </a>
            );
          })}
        </div>

        {/* User avatar + dropdown */}
        <div className="flex items-center gap-3" ref={menuRef}>
          <div className="status-dot" />
          <div className="relative">
            <button
              id="user-menu-btn"
              onClick={() => setMenuOpen(m => !m)}
              className="w-9 h-9 rounded-full border flex items-center justify-center text-xs font-bold transition-all duration-200"
              style={{
                background:  "rgba(201,168,76,0.12)",
                borderColor: "rgba(201,168,76,0.35)",
                color:       "#C9A84C",
                boxShadow:   menuOpen ? "0 0 16px rgba(201,168,76,0.3)" : "none",
              }}
            >
              {initials}
            </button>

            {menuOpen && (
              <div
                className="absolute right-0 top-12 w-56 rounded-xl overflow-hidden animate-fade-up"
                style={{ background:"rgba(10,14,26,0.98)", border:"1px solid rgba(201,168,76,0.22)", boxShadow:"0 16px 48px rgba(0,0,0,0.6)" }}
              >
                <div className="px-4 py-3" style={{ borderBottom:"1px solid rgba(201,168,76,0.12)" }}>
                  <p className="text-gold-300 text-sm font-semibold truncate">{user?.name || "User"}</p>
                  <p className="text-slate-500 text-xs truncate mt-0.5">{user?.email || ""}</p>
                  {user?.role && (
                    <span className="inline-block mt-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                      style={{ background:"rgba(201,168,76,0.12)", color:"#C9A84C", border:"1px solid rgba(201,168,76,0.25)" }}>
                      {user.role}
                    </span>
                  )}
                </div>

                <button
                  id="logout-btn"
                  onClick={() => { setMenuOpen(false); onLogout(); }}
                  className="w-full flex items-center gap-3 px-4 py-3 text-sm text-slate-400 hover:text-rose-400 hover:bg-rose-500/08 transition-all duration-200"
                >
                  <span>🚪</span>
                  <span className="font-semibold">Sign Out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="gold-divider" />
    </nav>
  );
}

// ─── Case Info Cards ─────────────────────────────────────────────────────────
function CaseMetaCard({ meta, caseNumber }) {
  if (!meta && !caseNumber) return null;
  const fields = [
    { label:"Case Number", value:caseNumber||meta?.case_number, mono:true, accent:true },
    { label:"Case Type",   value:meta?.case_type },
    { label:"Year",        value:meta?.case_year },
    { label:"Court",       value:meta?.court_name },
    { label:"Court Level", value:meta?.court_level },
    { label:"Judge",       value:meta?.judge_name },
    { label:"Petitioner",  value:meta?.petitioner },
    { label:"Respondent",  value:meta?.respondent },
  ].filter(f => f.value && f.value !== "unknown");
  if (fields.length === 0) return null;
  return (
    <div className="glass-card p-6 mb-8 animate-fade-up">
      <div className="flex items-center gap-3 mb-6 pb-4 border-b border-white/06">
        <span className="text-gold-400">📋</span>
        <h3 className="label-xs">Extracted Case Information</h3>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {fields.map(f => (
          <div key={f.label} className="rounded-xl p-3 border border-white/05" style={{background:"rgba(255,255,255,0.02)"}}>
            <span className="block label-xs mb-1" style={{fontSize:"9px"}}>{f.label}</span>
            <span className={`text-sm font-semibold block truncate ${
              f.accent ? "text-gold-300" : "text-slate-300"
            } ${f.mono ? "font-mono text-xs" : ""}`}>{f.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Feature Grid (replaces plain ActionBar) ─────────────────────────────────
function FeatureGrid({ caseNumber, onSummarize, onSimilar, loading, analysisRan }) {
  const features = [
    {
      id: "summarize",
      icon: "📋",
      label: "Summarize",
      desc: "Plain-language breakdown",
      color: "blue",
      auto: false,
      onClick: onSummarize,
      loading: loading.summarize,
    },
    {
      id: "similar",
      icon: "🔍",
      label: "Find Similar",
      desc: "Vector search across cases",
      color: "purple",
      auto: false,
      onClick: onSimilar,
      loading: loading.similar,
    },
    {
      id: "bns",
      icon: "📖",
      label: "BNS Mapper",
      desc: "Old Act → New Act mapping",
      color: "amber",
      auto: true,
      href: "#/bns",
    },
    {
      id: "adr",
      icon: "⚖️",
      label: "ADR Checker",
      desc: "Lok Adalat & settlement",
      color: "emerald",
      auto: true,
      href: "#/adr",
    },
    {
      id: "ecourts",
      icon: "🏛️",
      label: "eCourts Sync",
      desc: "Live hearing dates",
      color: "cyan",
      auto: false,
      href: "#/ecourts",
    },
    {
      id: "predict",
      icon: "🔮",
      label: "Outcome Model",
      desc: "Win probability prediction",
      color: "gold",
      auto: false,
      href: "#/predict",
    },
  ];

  const colorMap = {
    blue:    "border-blue-500/20   text-blue-300   hover:border-blue-400/40   hover:bg-blue-500/08",
    purple:  "border-purple-500/20 text-purple-300 hover:border-purple-400/40 hover:bg-purple-500/08",
    amber:   "border-amber-500/20  text-amber-300  hover:border-amber-400/40  hover:bg-amber-500/08",
    emerald: "border-emerald-500/20 text-emerald-300 hover:border-emerald-400/40 hover:bg-emerald-500/08",
    cyan:    "border-cyan-500/20   text-cyan-300   hover:border-cyan-400/40   hover:bg-cyan-500/08",
    gold:    "border-gold-400/20   text-gold-300   hover:border-gold-400/40   hover:bg-gold-400/08",
  };

  return (
    <div className="card mb-8">
      <div className="flex flex-col mb-6">
        <h3 className="label-xs">Run Analysis</h3>
        <p className="text-sm mt-1" style={{color:"var(--text-muted)"}}>Interactive modules for deep case intelligence</p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {features.map((f) => {
          const isDisabled = !caseNumber && !f.href;
          const content = (
            <div
              className={`flex flex-col items-center text-center p-4 rounded-xl border transition-all duration-200 group ${colorMap[f.color]} ${isDisabled ? "opacity-35 cursor-not-allowed" : "cursor-pointer active:scale-95"}`}
              style={{background:"rgba(255,255,255,0.025)"}}
              onClick={f.onClick && !isDisabled ? f.onClick : undefined}>
              <div className="text-2xl mb-3 group-hover:scale-110 transition-transform duration-200">
                {f.loading ? <span className="inline-block w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" /> : f.icon}
              </div>
              <div className="text-xs font-bold mb-1" style={{color:"var(--text-primary)"}}>{f.label}</div>
              <div className="text-[10px] leading-tight mb-2" style={{color:"var(--text-muted)"}}>{f.desc}</div>
              <div className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full" style={{background:"rgba(201,168,76,0.10)",color:"#C9A84C"}}>
                {f.auto ? "Auto" : "Manual"}
              </div>
            </div>
          );
          return f.href ? (
            <a key={f.id} href={f.href} className="no-underline">{content}</a>
          ) : (
            <div key={f.id}>{content}</div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Summary Panel ────────────────────────────────────────────────────────────
function SummaryPanel({ data, caseNumber, language, setLanguage, onTranslate, loading, translation }) {
  const s = data?.summary || {};
  const langOptions = [
    { code: "hi", label: "Hindi" },
    { code: "te", label: "Telugu" },
    { code: "kn", label: "Kannada" },
    { code: "ta", label: "Tamil" },
    { code: "ml", label: "Malayalam" },
    { code: "mr", label: "Marathi" },
    { code: "simple_en", label: "English (Simple)" },
  ];
  if (!data && !loading.summarize) return null;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 py-4">
        <div className="flex-1 gold-divider" />
        <h2 className="label-xs">Case Breakdown</h2>
        <div className="flex-1 gold-divider" />
      </div>

      {loading.summarize && (
        <div className="card animate-pulse flex flex-col items-center justify-center py-12">
          <div className="w-10 h-10 border-4 border-legal-200 border-t-legal-600 rounded-full animate-spin mb-4" />
          <p className="text-sm font-medium text-slate-500">Generating plain-language summary...</p>
        </div>
      )}

      {(s.short_summary || s.basic_summary) && (
        <div className="card hover:shadow-xl group">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-2 h-2 rounded-full bg-legal-600" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Quick Summary</h3>
          </div>
          {s.basic_summary && <div className="text-slate-700 leading-relaxed text-lg font-medium p-6 bg-slate-50 rounded-xl border border-slate-100 mb-6">{s.basic_summary}</div>}
          {s.short_summary && !s.basic_summary && <div className="text-slate-700 leading-relaxed text-lg font-medium p-6 bg-slate-50 rounded-xl border border-slate-100 mb-6">{s.short_summary}</div>}
          
          {s.key_points?.length > 0 && (
            <div className="mt-8">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">Key Legal Points</h4>
              <div className="space-y-3">
                {s.key_points.map((pt, i) => (
                  <div key={i} className="flex gap-4 p-4 rounded-lg bg-white border border-slate-100 hover:border-legal-200 transition-colors duration-200">
                    <div className="w-6 h-6 rounded-full bg-legal-50 text-legal-700 text-xs font-bold flex items-center justify-center shrink-0">
                      {i + 1}
                    </div>
                    <div className="text-sm text-slate-600 leading-relaxed">
                      {typeof pt === "object" && pt !== null
                        ? <><span className="font-bold text-slate-800">{pt.label}:</span> {pt.explanation}</>
                        : pt}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {caseNumber && (
        <div className="card border-l-4 border-l-cyan-500">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-2 h-2 rounded-full bg-cyan-500" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Read in your language</h3>
          </div>
          
          <div className="flex flex-wrap gap-2 mb-8">
            {langOptions.map((l) => (
              <button key={l.code}
                className={`px-4 py-2 rounded-full text-xs font-bold transition-all duration-200 border ${
                  language === l.code 
                    ? "bg-cyan-50 border-cyan-200 text-cyan-700 shadow-sm" 
                    : "bg-slate-50 border-slate-100 text-slate-400 hover:bg-white hover:border-slate-300"
                }`}
                onClick={() => setLanguage(l.code)}>
                {l.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <button className="btn bg-white border-2 border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300 gap-3"
              onClick={() => onTranslate("summary")} disabled={loading.translate}>
              {loading.translate ? <span className="w-4 h-4 border-2 border-slate-300 border-t-slate-600 rounded-full animate-spin" /> : "📋"}
              Translate Summary
            </button>
            <button className="btn bg-white border-2 border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300 gap-3"
              onClick={() => onTranslate("raw")} disabled={loading.translate}>
              {loading.translate ? <span className="w-4 h-4 border-2 border-slate-300 border-t-slate-600 rounded-full animate-spin" /> : "📄"}
              Translate Full Text
            </button>
          </div>

          {translation && (
            <div className="animate-in fade-in duration-500">
              {translation.error ? (
                <div className="bg-red-50 text-red-700 text-sm p-4 rounded-lg border border-red-100">
                  ⚠ Error: {translation.error}
                </div>
              ) : (
                <div className="bg-slate-900 text-slate-100 rounded-xl p-8 shadow-2xl relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                    <div className="text-8xl">文</div>
                  </div>
                  {translation.language_name && (
                    <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-cyan-400 mb-6 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                      {translation.language_name} • {translation.mode === "raw" ? "Full Text" : "Summary"}
                    </div>
                  )}
                  <div className="text-base leading-[2] whitespace-pre-wrap font-medium">
                    {translation.translated_text}
                  </div>
                  {translation.model_used && (
                    <div className="mt-8 pt-4 border-t border-white/10 flex justify-between items-center">
                      <div className="text-[10px] text-white/40 italic">Translated by {translation.model_used}</div>
                      <button className="text-white/40 hover:text-white text-xs transition-colors" 
                        onClick={() => navigator.clipboard.writeText(translation.translated_text)}>
                        Copy Text
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          
          {!translation && !loading.translate && (
            <div className="text-center py-8 border-2 border-dashed border-slate-100 rounded-xl">
              <p className="text-sm text-slate-400 font-medium">Select a language and choose what to translate</p>
            </div>
          )}
        </div>
      )}

      {(s.short_summary || s.basic_summary) && (
        <div className="bg-amber-50 border border-amber-100 rounded-xl p-6 flex gap-4">
          <div className="text-2xl mt-1">📌</div>
          <div>
            <h4 className="text-amber-800 font-bold text-sm mb-1">Neutral Guidance</h4>
            <p className="text-amber-700/80 text-sm leading-relaxed">
              This is an AI-generated educational explanation and does not constitute legal advice. 
              Always consult with a qualified advocate for official legal proceedings.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Case Viewer Modal ────────────────────────────────────────────────────────
function CaseViewer({ caseData, onClose }) {
  if (!caseData) return null;
  const meta = caseData.case_metadata || {};
  const sum = caseData.summary || {};
  const fields = [
    { label: "Case Number", value: caseData.case_number },
    { label: "Case Type",   value: meta.case_type },
    { label: "Year",        value: meta.case_year },
    { label: "Court",       value: meta.court_name },
    { label: "Judge",       value: meta.judge_name },
    { label: "Petitioner",  value: meta.petitioner },
    { label: "Respondent",  value: meta.respondent },
  ].filter((f) => f.value && f.value !== "unknown");

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 backdrop-blur-sm animate-fade-in" style={{background:"rgba(5,8,15,0.75)"}} onClick={onClose}>
      <div className="animate-scale-in max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col" style={{background:"rgba(17,19,28,0.98)",border:"1px solid rgba(201,168,76,0.18)",borderRadius:"20px",boxShadow:"0 24px 80px rgba(0,0,0,0.7)"}} onClick={(e) => e.stopPropagation()}>
        <div className="p-6 flex items-center justify-between sticky top-0 z-10" style={{borderBottom:"1px solid rgba(201,168,76,0.12)",background:"rgba(17,19,28,0.98)"}}>
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-gold-400" style={{boxShadow:"0 0 8px rgba(201,168,76,0.6)"}} />
            <h3 className="font-semibold text-base" style={{color:"var(--text-primary)",fontFamily:"'Cormorant Garamond',serif"}}>Similar Case — {caseData.case_number || "Reference"}</h3>
          </div>
          <button className="w-8 h-8 rounded-full flex items-center justify-center transition-all" style={{color:"var(--text-muted)"}} onClick={onClose}>✕</button>
        </div>
        
        <div className="p-6 overflow-y-auto space-y-6">
          {fields.length > 0 && (
            <div className="grid grid-cols-2 gap-3">
              {fields.map((f) => (
                <div key={f.label} className="p-3 rounded-xl" style={{background:"rgba(255,255,255,0.03)",border:"1px solid rgba(255,255,255,0.07)"}}>
                  <span className="block label-xs mb-1">{f.label}</span>
                  <span className="block text-sm font-semibold" style={{color:"var(--text-primary)"}}>{f.value}</span>
                </div>
              ))}
            </div>
          )}
          
          <div>
            <h4 className="label-xs mb-4">Case Summary</h4>
            {sum.basic_summary ? (
              <div className="legal-clause body-text">{sum.basic_summary}</div>
            ) : (
              <div className="text-center py-10" style={{border:"1px dashed rgba(255,255,255,0.08)",borderRadius:"12px"}}>
                <p className="text-sm italic" style={{color:"var(--text-muted)"}}>No summary available for this reference case.</p>
              </div>
            )}
          </div>
        </div>
        
        <div className="p-6 flex justify-end" style={{borderTop:"1px solid rgba(201,168,76,0.12)"}}>
          <button className="btn btn-primary" onClick={onClose}>Close Viewer</button>
        </div>
      </div>
    </div>
  );
}

// ─── Similar Cases Panel ──────────────────────────────────────────────────────
function SimilarCasesPanel({ data, loading, onCaseClick }) {
  if (!data && !loading.similar) return null;
  const kws = data?.keywords || [];
  const cases = data?.similar_cases || [];
  return (
    <div className="space-y-6 mt-12">
      <div className="flex items-center gap-4 py-4">
        <div className="flex-1 gold-divider" />
        <h2 className="label-xs">Precedent Database</h2>
        <div className="flex-1 gold-divider" />
      </div>

      {loading.similar && (
        <div className="card flex flex-col items-center justify-center py-12">
          <div className="w-10 h-10 border-2 border-t-gold-400 rounded-full animate-spin mb-4" style={{borderColor:"rgba(201,168,76,0.2)",borderTopColor:"#C9A84C"}} />
          <p className="text-sm" style={{color:"var(--text-muted)"}}>Searching global legal database…</p>
        </div>
      )}

      {kws.length > 0 && (
        <div className="card border-l-4 border-l-blue-500">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-2 h-2 rounded-full bg-blue-500" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Detected Legal Context</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {kws.map((k, i) => (
              <span key={i} className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-xs font-bold border border-blue-100">
                {k}
              </span>
            ))}
          </div>
        </div>
      )}

      {cases.length > 0 && (
        <div className="card" style={{borderLeft:"3px solid rgba(168,85,247,0.5)"}}>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-2 h-2 rounded-full" style={{background:"#a855f7",boxShadow:"0 0 10px rgba(168,85,247,0.5)"}} />
              <h3 className="label-xs">Top {cases.length} Match Analysis</h3>
            </div>
            <span className="label-xs" style={{color:"var(--text-muted)"}}>Click to inspect</span>
          </div>
          <div className="space-y-3">
            {cases.map((c, i) => (
              <div key={c.case_number || i}
                className="list-item cursor-pointer group"
                onClick={() => onCaseClick && c.case_id && onCaseClick(c.case_id)}>
                <div className="flex items-center gap-4 w-full">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-mono mb-1" style={{color:"#a855f7"}}>{c.case_number}</div>
                    <div className="text-sm font-semibold truncate" style={{color:"var(--text-primary)"}}>{c.title || "Untitled Judgment"}</div>
                  </div>
                  <div className="shrink-0 flex flex-col items-end">
                    <div className="text-lg font-bold" style={{color:"#3FB950"}}>{Math.round((c.similarity_score || 0) * 100)}%</div>
                    <div className="label-xs">Similarity</div>
                  </div>
                </div>
                <div className="progress-track mt-3 w-full">
                  <div className="progress-fill" style={{width:`${Math.round((c.similarity_score||0)*100)}%`,background:"linear-gradient(90deg,#3FB950,#22c55e)"}} />
                </div>
                {c.matched_keywords?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {c.matched_keywords.slice(0,5).map((k,j)=>(
                      <span key={j} className="tag tag-blue">{k}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {data && !loading.similar && cases.length === 0 && (
        <div className="card py-16 flex flex-col items-center">
          <div className="text-5xl mb-4 opacity-20">🔍</div>
          <p className="text-slate-400 font-medium italic">No direct legal precedents found in the database.</p>
        </div>
      )}
    </div>
  );
}

// ─── Upload Page ──────────────────────────────────────────────────────────────
function UploadPage() {
  const [uploadData, setUploadData] = useState(null);
  const [caseNumber, setCaseNumber] = useState("");
  const [language, setLanguage] = useState("hi");
  const [summary, setSummary] = useState(null);
  const [translation, setTranslation] = useState(null);
  const [similar, setSimilar] = useState(null);
  const [viewedCase, setViewedCase] = useState(null);
  const [loading, setLoading] = useState({ summarize: false, translate: false, similar: false, viewCase: false });
  const [errors, setErrors] = useState({});

  const setLoad = (k, v) => setLoading((l) => ({ ...l, [k]: v }));
  const setErr  = (k, v) => setErrors((e) => ({ ...e, [k]: v }));

  const handleUploaded = (data) => {
    setUploadData(data);
    setCaseNumber(data.case_number);
    setSummary(null); setTranslation(null); setSimilar(null);
  };

  const doSummarize = async () => {
    if (!caseNumber) return;
    setLoad("summarize", true); setErr("summarize", "");
    try { setSummary(await api(`/ai/summarize/${encodeURIComponent(caseNumber)}`)); }
    catch (e) { setErr("summarize", e.message); }
    finally { setLoad("summarize", false); }
  };

  const doTranslate = async (mode = "summary") => {
    if (!caseNumber) return;
    setLoad("translate", true); setErr("translate", "");
    try {
      const url = `/ai/translate/${encodeURIComponent(caseNumber)}?language=${encodeURIComponent(language)}&mode=${mode}`;
      setTranslation(await api(url));
    }
    catch (e) { setErr("translate", e.message); }
    finally { setLoad("translate", false); }
  };

  const doSimilar = async () => {
    if (!caseNumber) return;
    setLoad("similar", true); setErr("similar", "");
    try { setSimilar(await api(`/search/${encodeURIComponent(caseNumber)}`)); }
    catch (e) { setErr("similar", e.message); }
    finally { setLoad("similar", false); }
  };

  const doViewCase = async (caseId) => {
    setLoad("viewCase", true);
    try { setViewedCase(await api(`/ai/case/${encodeURIComponent(caseId)}`)); }
    catch (e) { setErr("similar", `Could not load case: ${e.message}`); }
    finally { setLoad("viewCase", false); }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 pb-24">
      {/* Hero */}
      <div className="bg-slate-900 text-white rounded-3xl p-10 sm:p-14 mb-10 relative overflow-hidden shadow-2xl animate-fade-up">
        <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-amber-500/05 rounded-full translate-y-1/2 -translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-4">
          <div className="text-4xl">⚖️</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight">Legal Document Intelligence</h1>
          <p className="text-slate-400 text-sm max-w-lg leading-relaxed">
            Upload any legal document — petitions, FIRs, or judgments.<br />Get an instant breakdown in your preferred language.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <span className="px-3 py-1 bg-gold-500/20 text-gold-300 rounded-full text-[10px] font-black uppercase tracking-widest border border-gold-500/20">AI Summary</span>
            <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-emerald-500/20">Multi-Language</span>
            <span className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-blue-500/20">Precedent Search</span>
          </div>
        </div>
      </div>

      <UploadZone onUploaded={handleUploaded} api={api} />

      {uploadData && (
        <div className="flex flex-wrap items-center justify-center gap-3 my-8 animate-fade-up">
          <div className="flex items-center gap-2 px-4 py-2 rounded-full border border-gold-400/20 bg-gold-400/06">
            <span className="label-xs" style={{fontSize:"9px"}}>ID</span>
            <span className="text-sm font-bold text-gold-300 font-mono">{uploadData.case_number}</span>
          </div>
          {uploadData.language_code && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/08 bg-white/03">
              <span className="label-xs" style={{fontSize:"9px"}}>Language</span>
              <span className="text-sm font-bold text-blue-400">{uploadData.language_code.toUpperCase()}</span>
            </div>
          )}
          {uploadData.paragraph_count > 0 && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/08 bg-white/03">
              <span className="label-xs" style={{fontSize:"9px"}}>Content</span>
              <span className="text-sm font-bold text-purple-400">{uploadData.paragraph_count} Paras</span>
            </div>
          )}
          <div className="flex items-center gap-2 px-4 py-2 rounded-full border border-emerald-500/25 bg-emerald-500/08">
            <span className="text-sm font-bold text-emerald-400">✓ Securely Processed</span>
          </div>
        </div>
      )}

      {uploadData && <CaseMetaCard meta={uploadData.case_metadata} caseNumber={uploadData.case_number} />}

      <FeatureGrid
        caseNumber={caseNumber}
        onSummarize={doSummarize}
        onSimilar={doSimilar}
        loading={loading}
      />

      {/* Unified Intelligence Card — shows after upload */}
      {caseNumber && (
        <div className="mb-8 animate-in slide-in-from-bottom-4 duration-500">
          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-slate-200" />
            <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">Live Intelligence Dashboard</h2>
            <div className="flex-1 h-px bg-slate-200" />
          </div>
          <div className="grid grid-cols-1 gap-8">
            <ADRPanel caseNumber={caseNumber} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-12">
        <SummaryPanel
          data={summary} caseNumber={caseNumber}
          language={language} setLanguage={setLanguage}
          onTranslate={doTranslate} loading={loading} translation={translation}
        />
        
        <SimilarCasesPanel data={similar} loading={loading} onCaseClick={doViewCase} />
      </div>

      {Object.entries(errors).map(([k,v]) => v ? (
        <div key={k} className="mt-6 p-4 rounded-xl border border-rose-500/20 bg-rose-500/08 flex items-center gap-3 animate-fade-up">
          <span className="text-rose-400">⚠</span>
          <span className="text-rose-300 text-sm"><strong className="uppercase tracking-widest text-[10px]">{k}:</strong> {v}</span>
        </div>
      ) : null)}

      {(loading.viewCase || viewedCase) && (
        <CaseViewer
          caseData={loading.viewCase ? null : viewedCase}
          onClose={() => setViewedCase(null)}
        />
      )}

      {/* Workspace history */}
      <div className="mt-20">
        <div className="flex items-center gap-4 mb-8">
          <div className="flex-1 gold-divider" />
          <h2 className="label-xs">Personal Workspace History</h2>
          <div className="flex-1 gold-divider" />
        </div>
        <RecentCasesPanel api={api} />
      </div>

      <Chatbot api={api} caseNumber={caseNumber} language={language} setLanguage={setLanguage} />
    </div>
  );
}

// ─── ADR Page ─────────────────────────────────────────────────────────────────
function ADRPage() {
  const [caseNumberRaw, setCaseNumberRaw] = useState("");
  const [caseNumberDebounced, setCaseNumberDebounced] = useState("");
  const [mode, setMode] = useState("lookup"); // lookup | manual
  const [manualResult, setManualResult] = useState(null);
  const adrDebounceRef = useRef(null);

  const handleCaseNumberChange = (val) => {
    setCaseNumberRaw(val);
    if (adrDebounceRef.current) clearTimeout(adrDebounceRef.current);
    if (!val.trim() || val.trim().length < 5) {
      setCaseNumberDebounced("");
      return;
    }
    adrDebounceRef.current = setTimeout(() => {
      setCaseNumberDebounced(val.trim());
    }, 800);
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {/* Hero */}
      <div className="bg-slate-900 text-white rounded-3xl p-10 sm:p-14 mb-10 relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-amber-500/05 rounded-full translate-y-1/2 -translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-4">
          <div className="text-4xl">⚖️</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight">ADR Suitability Predictor</h1>
          <p className="text-slate-400 text-sm max-w-lg leading-relaxed">
            NALSA-informed scoring for Lok Adalat eligibility, settlement range, and AI-drafted referral applications.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-emerald-500/20">4 ADR Pathways</span>
            <span className="px-3 py-1 bg-amber-500/20 text-amber-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-amber-500/20">NALSA Benchmarks</span>
            <span className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-blue-500/20">AI Draft Generator</span>
          </div>
        </div>
      </div>

      {/* Mode toggle */}
      <div className="tab-bar mb-8">
        {[
          { id: "lookup", label: "🔍 Case Lookup", desc: "By case number" },
          { id: "manual", label: "📝 Manual Assessment", desc: "Enter details directly" },
        ].map(m => (
          <button key={m.id} onClick={() => { setMode(m.id); setManualResult(null); }}
            className={`tab-btn${mode === m.id ? " active" : ""}`}>
            <span className="text-sm font-semibold">{m.label}</span>
            <span className="text-[10px] mt-0.5 hidden sm:block" style={{color:"var(--text-muted)"}}>{m.desc}</span>
          </button>
        ))}
      </div>

      {/* Case Lookup mode */}
      {mode === "lookup" && (
        <>
          <div className="card mb-8">
            <label className="block label-xs mb-3">Case Number</label>
            <input
              className="gold-input text-base font-mono"
              placeholder="e.g. CRLMP/5422/2023 or CNR number"
              value={caseNumberRaw}
              onChange={e => handleCaseNumberChange(e.target.value)}
            />
            {caseNumberRaw && !caseNumberDebounced && (
              <p className="text-xs mt-2" style={{color:"#E3B341"}}>⏳ Waiting for you to finish typing…</p>
            )}
          </div>
          {caseNumberDebounced ? (
            <ADRPanel caseNumber={caseNumberDebounced} fullPage />
          ) : (
            <div className="py-24 text-center border-2 border-dashed border-slate-200 rounded-3xl opacity-50">
              <div className="text-6xl mb-6">🔍</div>
              <p className="text-slate-400 font-bold italic">
                {caseNumberRaw
                  ? "Waiting for you to finish typing the case number…"
                  : "Enter a case number to load the stored ADR assessment."}
              </p>
            </div>
          )}
        </>
      )}

      {/* Manual Assessment mode */}
      {mode === "manual" && (
        <div className="space-y-8 animate-in fade-in duration-300">
          <ManualADRForm onResult={setManualResult} />
          {manualResult && <ADRPanel caseNumber={manualResult.case_number} overrideData={manualResult} fullPage />}
        </div>
      )}
    </div>
  );
}


// ─── BNS Page ─────────────────────────────────────────────────────────────────
function BNSPage() {
  const [tab, setTab] = useState("lookup");
  const TABS = [
    { id: "lookup",  label: "🔍 Section Lookup",    desc: "Search by act & section" },
    { id: "analyze", label: "📄 FIR Analyzer",       desc: "Extract citations from text" },
    { id: "rewrite", label: "✏️ Draft Rewriter",     desc: "Auto-update to BNS" },
  ];
  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {/* Hero */}
      <div className="bg-slate-900 text-white rounded-3xl p-10 sm:p-14 mb-10 relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-amber-500/05 rounded-full translate-y-1/2 -translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-4">
          <div className="text-4xl">📖</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight">BNS Section Mapper</h1>
          <p className="text-slate-400 text-sm max-w-lg leading-relaxed">
            IPC · CrPC · IEA → BNS · BNSS · BSA. 80+ official mappings from the MHA gazette. Effective July 1, 2024.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <span className="px-3 py-1 bg-amber-500/20 text-amber-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-amber-500/20">80+ Sections Mapped</span>
            <span className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-blue-500/20">Bidirectional</span>
            <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-emerald-500/20">AI Draft Rewriter</span>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="tab-bar mb-8">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`tab-btn${tab === t.id ? " active" : ""}`}>
            <span className="text-sm">{t.label}</span>
            <span className="text-[10px] mt-0.5 hidden sm:block" style={{color:"var(--text-muted)"}}>{t.desc}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="animate-in fade-in duration-300">
        {tab === "lookup"  && <SectionLookupPage />}
        {tab === "analyze" && <DraftAnalyzer />}
        {tab === "rewrite" && <DocumentRewriter />}
      </div>
    </div>
  );
}

// ─── eCourts Page ─────────────────────────────────────────────────────────────
// CNR validation helper – must be 16 alphanumeric chars, uppercase
function isValidCnr(val) {
  if (!val) return false;
  const cleaned = val.replace(/[\s-]/g, "").toUpperCase();
  // CNR format: 4 alpha + 9-12 digits = 13-16 total alphanumeric
  return /^[A-Z]{4}\d{9,12}$/.test(cleaned) || cleaned.length >= 16;
}

function EcourtsPage() {
  const [tab, setTab] = useState("guide"); // guide | sync
  // Raw typed values (update on every keystroke for UI)
  const [caseNumberRaw, setCaseNumberRaw] = useState("");
  const [cnrRaw, setCnrRaw]               = useState("");
  // Debounced values (only update after 800ms pause — used to trigger API)
  const [caseNumberDebounced, setCaseNumberDebounced] = useState("");
  const debounceRef = useRef(null);

  // Debounce: wait 800ms after last keystroke before accepting caseNumber
  const handleCaseNumberChange = (val) => {
    setCaseNumberRaw(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!val.trim() || val.trim().length < 5) {
      // Reset immediately for very short/empty inputs to avoid stale panel
      setCaseNumberDebounced("");
      return;
    }
    debounceRef.current = setTimeout(() => {
      setCaseNumberDebounced(val.trim());
    }, 800);
  };

  const TABS = [
    { id: "guide", icon: "🤖", label: "AI Guide",  desc: "Smart portal navigation" },
    { id: "sync",  icon: "🔄", label: "Live Sync",  desc: "CAPTCHA-based data sync" },
  ];

  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {/* Hero */}
      <div className="bg-slate-900 text-white rounded-3xl p-10 sm:p-14 mb-10 relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-cyan-500/05 rounded-full translate-y-1/2 -translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-4">
          <div className="text-4xl">🏛️</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight">eCourts Intelligence</h1>
          <p className="text-slate-400 text-sm max-w-lg leading-relaxed">
            AI-guided portal navigation · Real-time NJDG sync · Auto BNS mapping from pasted case data.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <span className="px-3 py-1 bg-cyan-500/20 text-cyan-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-cyan-500/20">6 Search Methods</span>
            <span className="px-3 py-1 bg-amber-500/20 text-amber-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-amber-500/20">BNS Auto-Mapping</span>
            <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-emerald-500/20">CAPTCHA Live Sync</span>
          </div>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2 mb-8">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className="flex-1 flex flex-col items-center py-4 px-4 rounded-2xl border text-center transition-all"
            style={tab === t.id
              ? {background:"rgba(201,168,76,0.12)",borderColor:"rgba(201,168,76,0.40)",color:"#C9A84C",boxShadow:"0 0 20px rgba(201,168,76,0.10)"}
              : {background:"rgba(255,255,255,0.03)",borderColor:"rgba(255,255,255,0.08)",color:"var(--text-muted)"}}>
            <span className="text-xl mb-1">{t.icon}</span>
            <span className="text-sm font-black">{t.label}</span>
            <span className="text-[10px] mt-0.5 opacity-60 hidden sm:block">{t.desc}</span>
          </button>
        ))}
      </div>

      {/* AI Guide tab */}
      {tab === "guide" && (
        <div className="animate-in fade-in duration-300">
          <ECourtsAssistant />
        </div>
      )}

      {/* Live Sync tab */}
      {tab === "sync" && (
        <div className="animate-in fade-in duration-300 space-y-8">
        <div className="card">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="form-label ml-1">Case Number</label>
                <input
                  className="gold-input font-mono font-bold"
                  placeholder="e.g. OS/105/2024"
                  value={caseNumberRaw}
                  onChange={e => handleCaseNumberChange(e.target.value)}
                />
                {caseNumberRaw && !caseNumberDebounced && (
                  <p className="text-[10px] font-bold ml-1" style={{color:"#E3B341"}}>⏳ Waiting for you to finish typing…</p>
                )}
              </div>
              <div className="space-y-2">
                <label className="form-label ml-1">CNR Number (Optional)</label>
                <input
                  className="gold-input"
                  style={{fontFamily:"'IBM Plex Mono',monospace",fontWeight:700}}
                  placeholder="e.g. MHPN0100..."
                  value={cnrRaw}
                  onChange={e => setCnrRaw(e.target.value)}
                />
              </div>
            </div>
          </div>
          {caseNumberDebounced ? (
            <ECourtsPanel caseNumber={caseNumberDebounced} cnrNumber={cnrRaw.trim() || undefined} fullPage />
          ) : (
            <div className="py-24 text-center rounded-3xl opacity-60" style={{border:"2px dashed rgba(201,168,76,0.25)"}}>
              <div className="text-6xl mb-6">🔄</div>
              <p className="font-bold italic" style={{color:"var(--text-muted)"}}>
                {caseNumberRaw
                  ? "Waiting for you to finish typing the case number…"
                  : "Enter a case number above to start CAPTCHA-based live sync."}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────
export default function App() {
  const { user, login, logout } = useAuth();
  const hash = useHash();
  const page = hash.replace("#", "").replace(/^\//, "") || "/";
  const activeNav = NAV_ITEMS.find(n => hash.startsWith(n.href) && n.href !== "#/")?.href
    || (hash === "#/" || hash === "#" ? "#/" : "#/");

  // Auth gate — show AuthPage when no user session
  if (!user) {
    return <AuthPage onAuth={login} />;
  }

  return (
    <>
      <NavBar active={activeNav} user={user} onLogout={logout} />
      {page === "predict"      && <PredictionPage onBack={() => { window.location.hash = "#/"; }} />}
      {page === "adr"          && <ADRPage />}
      {page === "bns"          && <BNSPage />}
      {page === "ecourts"      && <EcourtsPage />}
      {page === "intelligence" && <IntelligenceDashboard />}
      {(page === "/" || page === "") && <UploadPage />}
    </>
  );
}
