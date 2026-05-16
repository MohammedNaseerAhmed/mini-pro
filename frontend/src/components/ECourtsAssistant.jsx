import { useState } from "react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// ── Method icon colours ───────────────────────────────────────────────────────
const METHOD_COLORS = {
  cnr:         { bg: "bg-cyan-50",    border: "border-cyan-200",   text: "text-cyan-800",   badge: "bg-cyan-100 text-cyan-700"   },
  case_number: { bg: "bg-blue-50",    border: "border-blue-200",   text: "text-blue-800",   badge: "bg-blue-100 text-blue-700"   },
  party_name:  { bg: "bg-violet-50",  border: "border-violet-200", text: "text-violet-800", badge: "bg-violet-100 text-violet-700"},
  fir:         { bg: "bg-red-50",     border: "border-red-200",    text: "text-red-800",    badge: "bg-red-100 text-red-700"     },
  advocate:    { bg: "bg-amber-50",   border: "border-amber-200",  text: "text-amber-800",  badge: "bg-amber-100 text-amber-700" },
  act_section: { bg: "bg-emerald-50", border: "border-emerald-200",text: "text-emerald-800",badge: "bg-emerald-100 text-emerald-700"},
};

const CONFIDENCE_LABEL = { high: "✓ High Confidence", medium: "~ Medium Confidence", low: "? Low Confidence" };
const CONFIDENCE_CLR   = { high: "text-emerald-600", medium: "text-amber-600", low: "text-slate-400" };

// ── Step 1: Query Input ───────────────────────────────────────────────────────
function QueryInput({ onGuide }) {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!q.trim()) return;
    setLoading(true); setErr("");
    try {
      const res = await fetch(`${API}/ecourts/guide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Guide request failed");
      onGuide(data);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  };

  const EXAMPLES = [
    { label: "I have a CNR number", value: "MHAU019999992015" },
    { label: "Case number known", value: "WP/2345/2023" },
    { label: "Search by my name", value: "Ramesh Kumar Sharma" },
    { label: "FIR number", value: "FIR No 145/2022 Banjara Hills police station" },
    { label: "Advocate search", value: "Advocate Suresh Reddy cases" },
    { label: "By act/section", value: "IPC 420 cases" },
  ];

  return (
    <div className="space-y-6">
      {/* Hero info banner */}
      <div className="flex gap-4 p-5 bg-cyan-50 border border-cyan-100 rounded-2xl">
        <div className="text-2xl mt-0.5">🏛️</div>
        <div>
          <div className="text-sm font-black text-cyan-900 mb-1">eCourts AI Search Guide</div>
          <p className="text-xs text-cyan-700 leading-relaxed">
            Tell us what information you have about your case. We'll show you the exact steps to
            find it on the <strong>official eCourts portal</strong> — including how to handle the CAPTCHA.
          </p>
        </div>
      </div>

      {/* Input */}
      <div className="space-y-3">
        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
          What information do you have about your case?
        </label>
        <textarea
          id="ecourts-query-input"
          rows={3}
          className="gold-textarea"
          style={{ minHeight: "96px", fontSize: "0.9rem" }}
          placeholder={"Examples:\n\u2022 MHAU019999992015  (CNR number)\n\u2022 WP/2345/2023  (case number)\n\u2022 Ramesh Kumar vs State of Telangana\n\u2022 FIR No 145/2022 Banjara Hills"}
          value={q}
          onChange={e => setQ(e.target.value)}
        />
        {err && <p className="text-xs text-red-600 font-semibold px-1">⚠ {err}</p>}
      </div>

      {/* Quick-pick examples */}
      <div>
        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 ml-1">Quick Examples</div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(ex => (
            <button key={ex.label}
              className="px-3 py-1.5 text-xs font-semibold rounded-full transition-all"
              style={{background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.10)",color:"var(--text-muted)"}}
              onMouseEnter={e=>{e.currentTarget.style.borderColor="rgba(201,168,76,0.40)";e.currentTarget.style.color="#C9A84C";}}
              onMouseLeave={e=>{e.currentTarget.style.borderColor="rgba(255,255,255,0.10)";e.currentTarget.style.color="var(--text-muted)";}}
              onClick={() => setQ(ex.value)}>
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      <button
        id="ecourts-guide-btn"
        className="btn btn-primary w-full h-12 text-xs gap-3"
        onClick={submit}
        disabled={loading || !q.trim()}>
        {loading
          ? <><span className="inline-block w-4 h-4 border-2 rounded-full animate-spin" style={{borderColor:"rgba(10,14,26,0.3)",borderTopColor:"#0A0E1A"}} /> Detecting search method…</>
          : <><span>🔍</span> Find My Case — Show Me How</>}
      </button>
    </div>
  );
}

// ── Step 2: Guide Display ─────────────────────────────────────────────────────
function GuideDisplay({ guide, onReset, onAnalyze }) {
  const [showAll, setShowAll] = useState(false);
  const c = METHOD_COLORS[guide.method] || METHOD_COLORS.case_number;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">

      {/* Detected method header */}
      <div className={`${c.bg} ${c.border} border rounded-2xl p-5`}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="text-3xl">{guide.method_icon}</div>
            <div>
              <div className={`text-sm font-black ${c.text}`}>{guide.method_title}</div>
              <div className="text-xs text-slate-500 mt-0.5">{guide.description}</div>
            </div>
          </div>
          <div className="shrink-0 flex flex-col items-end gap-1">
            <span className={`text-[10px] font-black ${CONFIDENCE_CLR[guide.confidence]}`}>
              {CONFIDENCE_LABEL[guide.confidence]}
            </span>
            {guide.detected_value && (
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-black ${c.badge}`}>
                {guide.detected_value.length > 25 ? guide.detected_value.slice(0, 25) + "…" : guide.detected_value}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="glass-card overflow-hidden">
        <div className="px-6 py-4 flex items-center gap-2" style={{borderBottom:"1px solid var(--border-gold)"}}>
          <span className="text-base">📋</span>
          <span className="label-xs">Step-by-Step Instructions</span>
        </div>
        <div className="p-6 space-y-3">
          {guide.steps.map((step, i) => (
            <div key={i} className="flex gap-4 p-3 rounded-xl transition-colors" style={{}} onMouseEnter={e=>e.currentTarget.style.background="rgba(255,255,255,0.03)"} onMouseLeave={e=>e.currentTarget.style.background=""}>
              <div className="w-6 h-6 shrink-0 rounded-full text-xs font-black flex items-center justify-center mt-0.5" style={{background:"rgba(201,168,76,0.15)",color:"#C9A84C",border:"1px solid rgba(201,168,76,0.30)"}}>
                {i + 1}
              </div>
              <div className="text-sm leading-relaxed whitespace-pre-line" style={{color:"var(--text-secondary)"}}>{step}</div>
            </div>
          ))}
        </div>

        {/* Open portal CTA */}
        <div className="px-6 pb-6">
          <a
            href={guide.portal_url}
            target="_blank"
            rel="noreferrer"
            id="ecourts-portal-link"
            className="btn btn-primary flex items-center justify-center gap-3 w-full h-12 text-xs">
            <span>🌐</span> Open Official eCourts Portal
          </a>
        </div>
      </div>

      {/* Tips */}
      {guide.tips?.length > 0 && (
        <div className="rounded-2xl p-5 space-y-2" style={{background:"rgba(227,179,65,0.07)",border:"1px solid rgba(227,179,65,0.20)"}}>
          <div className="text-[10px] font-black uppercase tracking-widest mb-3" style={{color:"#E3B341"}}>💡 Tips</div>
          {guide.tips.map((tip, i) => (
            <div key={i} className="flex gap-2 text-xs" style={{color:"rgba(227,179,65,0.75)"}}>
              <span className="shrink-0 mt-0.5">•</span>
              <span>{tip}</span>
            </div>
          ))}
        </div>
      )}

      {/* Results info */}
      <div className="bg-slate-900 rounded-2xl p-5 space-y-2">
        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">📊 What the Results Show</div>
        {["Case Type and Number", "Filing & Registration Date", "CNR Number — save this!", "Petitioner & Respondent names", "Court Name, District, State", "Case Stage / Current Status", "Next Hearing Date", "Acts and Sections invoked", "History of hearings", "Orders/Judgments (as PDF where available)"].map((item, i) => (
          <div key={i} className="flex gap-2 text-xs text-slate-400">
            <span className="text-cyan-500 shrink-0">✓</span>
            <span>{item}</span>
          </div>
        ))}
      </div>

      {/* Other methods */}
      <div>
        <button className="text-xs text-slate-400 font-semibold hover:text-slate-600 mb-3 transition-colors"
          onClick={() => setShowAll(v => !v)}>
          {showAll ? "▲ Hide" : "▼ Show"} other search methods
        </button>
        {showAll && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 animate-in fade-in duration-300">
            {guide.all_methods?.filter(m => m.id !== guide.method).map(m => {
              const mc = METHOD_COLORS[m.id] || METHOD_COLORS.case_number;
              return (
                <div key={m.id} className={`${mc.bg} ${mc.border} border rounded-xl p-3 cursor-default`}>
                  <div className="text-xl mb-1">{m.icon}</div>
                  <div className={`text-xs font-black ${mc.text} leading-tight`}>{m.title}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Post-search: paste and analyze */}
      <div className="bg-gradient-to-br from-slate-900 to-cyan-950 rounded-2xl p-6 border border-cyan-900/30">
        <div className="text-[10px] font-black text-cyan-400 uppercase tracking-widest mb-2">⚡ After Your Search</div>
        <p className="text-sm text-slate-300 leading-relaxed mb-4">{guide.post_search_tip}</p>
        <button
          id="ecourts-paste-btn"
          className="h-10 px-6 bg-cyan-600 text-white rounded-xl text-xs font-black uppercase tracking-widest hover:bg-cyan-500 active:scale-95 transition-all"
          onClick={onAnalyze}>
          📋 Paste &amp; Analyze Case Data →
        </button>
      </div>

      <button className="text-xs text-slate-400 hover:text-slate-600 font-semibold transition-colors" onClick={onReset}>
        ← Start New Search
      </button>
    </div>
  );
}

// ── Step 3: Paste & Analyze ───────────────────────────────────────────────────
function PasteAnalyze({ onBack }) {
  const [text, setText] = useState("");
  const [caseRef, setCaseRef] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!text.trim()) return;
    setLoading(true); setErr(""); setResult(null);
    try {
      const res = await fetch(`${API}/ecourts/analyze-pasted`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pasted_text: text, case_number: caseRef || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Analysis failed");
      setResult(data);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  };

  const URGENCY_STYLE = {
    critical: "bg-red-500 text-white animate-pulse",
    high:     "bg-amber-500 text-white",
    medium:   "bg-yellow-100 text-yellow-800",
    low:      "bg-emerald-100 text-emerald-700",
    unknown:  "bg-slate-100 text-slate-500",
    past:     "bg-slate-100 text-slate-400",
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center gap-3">
        <button className="label-xs hover:text-gold-400 transition-colors" onClick={onBack}>← Back</button>
        <div className="text-sm font-black" style={{color:"var(--text-primary)"}}>Paste &amp; Analyze Case Data</div>
      </div>

      <div className="rounded-2xl p-4 text-xs leading-relaxed" style={{background:"rgba(59,130,246,0.07)",border:"1px solid rgba(59,130,246,0.20)",color:"rgba(147,197,253,0.85)"}}>
        📋 After finding your case on eCourts, <strong>select all text on the result page</strong> (Ctrl+A), copy it, and paste it below.
        We'll automatically extract CNR, parties, hearing dates, and map all legal sections to BNS.
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="sm:col-span-2 space-y-2">
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Pasted Case Text</label>
          <textarea
            id="ecourts-paste-area"
            rows={8}
            className="gold-textarea"
            style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "0.85rem", minHeight: "180px" }}
            placeholder="Paste text copied from the eCourts portal result page here…"
            value={text}
            onChange={e => setText(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Case Ref (optional)</label>
          <input
            className="gold-input"
            placeholder="Your internal case ID"
            value={caseRef}
            onChange={e => setCaseRef(e.target.value)}
          />
          <p className="text-[10px] text-slate-400 px-1 leading-relaxed">
            If provided, the extracted CNR and mapping data will be saved against this case reference.
          </p>
        </div>
      </div>

      {err && <p className="text-xs text-red-600 font-semibold px-1">⚠ {err}</p>}

      <button
        id="ecourts-analyze-submit"
        className="btn btn-primary w-full h-12 text-xs gap-3"
        onClick={submit}
        disabled={loading || !text.trim()}>
        {loading
          ? <><span className="inline-block w-4 h-4 border-2 rounded-full animate-spin" style={{borderColor:"rgba(10,14,26,0.3)",borderTopColor:"#0A0E1A"}} /> Analyzing…</>
          : <><span>⚡</span> Analyze Case Data</>}
      </button>

      {/* Results */}
      {result && (
        <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">

          {/* CNR + Parties */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px rounded-2xl overflow-hidden" style={{background:"var(--border-gold)",border:"1px solid var(--border-gold)"}}>
            {[
              { label: "CNR Number", value: result.cnr_number || "Not detected", mono: true, accent: result.cnr_number ? "cyan" : "none" },
              { label: "Petitioner", value: result.parties?.petitioner || "—" },
              { label: "Respondent", value: result.parties?.respondent || "—" },
              { label: "Next Hearing", value: result.next_hearing || "—", accent: result.next_hearing ? "amber" : "none" },
            ].map(({ label, value, mono, accent }) => (
              <div key={label} style={{background:"var(--bg-elevated)"}} className="p-5">
                <div className="label-xs mb-2">{label}</div>
                <div className={`text-sm font-black tracking-tight ${mono ? "font-mono" : ""} ${
                  accent === "cyan" ? "text-cyan-400" : accent === "amber" ? "text-amber-400" : ""
                }`} style={accent==="none"?{color:"var(--text-primary)"}:{}}>{value}</div>
              </div>
            ))}
          </div>

          {/* Urgency */}
          {result.urgency && result.urgency.level !== "unknown" && (
            <div className={`px-4 py-3 rounded-xl text-xs font-black flex items-center gap-2 ${URGENCY_STYLE[result.urgency.level] || URGENCY_STYLE.unknown}`}>
              {result.urgency.level === "critical" && "🚨"}
              {result.urgency.level === "high" && "⚠"}
              Next Hearing: {result.urgency.label}
            </div>
          )}

          {/* CNR saved */}
          {result.cnr_number && (
            <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-xs font-semibold ${
              result.cnr_saved ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-slate-50 border-slate-200 text-slate-500"
            }`}>
              <span>{result.cnr_saved ? "✓" : "ℹ"}</span>
              <span>CNR <strong className="font-mono">{result.cnr_number}</strong> — {result.cnr_saved ? "saved to your database" : "found but not saved (no case reference given)"}</span>
            </div>
          )}

          {/* BNS Mapping */}
          <div className="glass-card overflow-hidden">
            <div className="px-6 py-4 flex items-center justify-between" style={{borderBottom:"1px solid var(--border-gold)"}}>
              <div className="flex items-center gap-2">
                <span>📖</span>
                <span className="label-xs">BNS Section Mapping</span>
              </div>
              <div className="flex gap-3 text-[10px] font-black">
                <span style={{color:"var(--text-muted)"}}>{result.section_mapping.total_sections} sections</span>
                <span className="text-emerald-400">{result.section_mapping.mapped_count} mapped</span>
                {result.section_mapping.deprecated_found && (
                  <span className="text-amber-400">⚠ deprecated found</span>
                )}
              </div>
            </div>
            {result.section_mapping.sections.length > 0 ? (
              <div className="divide-y" style={{borderColor:"rgba(255,255,255,0.04)"}}>
                {result.section_mapping.sections.map((s, i) => (
                  <div key={i} className="px-6 py-4 flex items-center gap-4 transition-colors" onMouseEnter={e=>e.currentTarget.style.background="rgba(255,255,255,0.02)"} onMouseLeave={e=>e.currentTarget.style.background=""}>
                    <div className="w-24 shrink-0">
                      <span className="px-2 py-0.5 text-xs font-mono font-black rounded" style={{background:"rgba(255,255,255,0.07)",color:"var(--text-secondary)"}}>{s.act} {s.section}</span>
                    </div>
                    <div style={{color:"var(--text-muted)"}} className="text-lg shrink-0">→</div>
                    <div>
                      {s.mapped && s.new_act ? (
                        <>
                          <span className="px-2 py-0.5 text-xs font-mono font-black rounded" style={{background:"rgba(0,180,200,0.12)",color:"rgba(100,220,240,0.9)"}}>{s.new_act} {s.new_section}</span>
                          {s.new_title && <span className="ml-2 text-xs" style={{color:"var(--text-muted)"}}>{s.new_title}</span>}
                        </>
                      ) : (
                        <span className="text-xs italic" style={{color:"var(--text-muted)"}}>No mapping found</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-6 py-10 text-center text-sm" style={{color:"var(--text-muted)"}}>
                No legal sections detected in the pasted text.
              </div>
            )}
          </div>

          {/* ADR hint */}
          <div className={`flex items-center gap-4 p-5 rounded-2xl border ${
            result.adr_eligibility_hint === "possible"
              ? "bg-emerald-50 border-emerald-200"
              : "bg-slate-50 border-slate-200"
          }`}>
            <span className="text-2xl">{result.adr_eligibility_hint === "possible" ? "⚖️" : "🔍"}</span>
            <div>
              <div className={`text-sm font-black ${result.adr_eligibility_hint === "possible" ? "text-emerald-800" : "text-slate-600"}`}>
                ADR / Lok Adalat: {result.adr_eligibility_hint === "possible" ? "Possibly Eligible" : "Further Check Required"}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                {result.adr_eligibility_hint === "possible"
                  ? "Civil matter keywords detected. Run a full ADR assessment from the ADR Checker tab."
                  : "Use the ADR Checker tab for a detailed suitability analysis."}
              </div>
            </div>
            <a href="#/adr" className="ml-auto shrink-0 px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl text-xs font-black hover:border-emerald-300 hover:text-emerald-700 transition-colors">
              ADR Check →
            </a>
          </div>

          {/* Actions taken */}
          <div className="space-y-2">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Actions Completed</div>
            {result.actions_taken?.map((a, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-600">
                <span className="text-emerald-500 font-black">✓</span> {a}
              </div>
            ))}
          </div>

          {/* Next steps */}
          {result.next_steps?.length > 0 && (
            <div className="bg-slate-900 rounded-2xl p-5 space-y-2">
              <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">→ Recommended Next Steps</div>
              {result.next_steps.map((s, i) => (
                <div key={i} className="flex gap-2 text-xs text-slate-300">
                  <span className="text-cyan-400 shrink-0 font-black">{i + 1}.</span>
                  <span>{s}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Export ───────────────────────────────────────────────────────────────
export default function ECourtsAssistant() {
  const [step, setStep] = useState("input");   // input | guide | paste
  const [guide, setGuide] = useState(null);

  const handleGuide = (data) => { setGuide(data); setStep("guide"); };
  const handleAnalyze = () => setStep("paste");
  const handleReset = () => { setGuide(null); setStep("input"); };

  return (
    <div className="glass-card overflow-hidden">
      {/* Header */}
      <div className="px-8 py-6 flex items-center gap-4" style={{background:"rgba(5,8,15,0.6)",borderBottom:"1px solid var(--border-gold)"}}>
        <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl" style={{background:"rgba(201,168,76,0.10)",border:"1px solid rgba(201,168,76,0.30)"}}>🤖</div>
        <div>
          <div className="text-sm font-black uppercase tracking-[0.2em]" style={{color:"var(--text-primary)"}}>eCourts AI Guide</div>
          <div className="text-[10px] font-bold uppercase tracking-widest mt-0.5" style={{color:"#C9A84C"}}>
            Smart portal navigation · 6 search methods · BNS auto-mapping
          </div>
        </div>
        {/* Step indicator */}
        <div className="ml-auto flex items-center gap-2">
          {["input", "guide", "paste"].map((s, i) => (
            <div key={s} className={`w-2 h-2 rounded-full transition-all ${step === s ? "scale-125" : ""}`}
              style={{background: step === s ? "#C9A84C" : "rgba(255,255,255,0.15)"}} />
          ))}
        </div>
      </div>

      <div className="p-8">
        {step === "input" && <QueryInput onGuide={handleGuide} />}
        {step === "guide" && guide && (
          <GuideDisplay guide={guide} onReset={handleReset} onAnalyze={handleAnalyze} />
        )}
        {step === "paste" && <PasteAnalyze onBack={() => setStep("guide")} />}
      </div>
    </div>
  );
}
