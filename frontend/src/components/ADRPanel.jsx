import { useState, useEffect, useCallback, useRef } from "react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// ── Case-number client-side pre-validation ────────────────────────────────────
// Returns true only when the value looks complete enough to query the backend.
function isValidCaseNumberForFetch(val) {
  if (!val) return false;
  const cleaned = val.replace(/[\s-]/g, "").toUpperCase();
  if (cleaned.length < 5) return false;          // too short
  if (!/\d/.test(cleaned)) return false;          // must have at least one digit
  return true;
}

// ── Score styles ──────────────────────────────────────────────────────────────
const SCORE_STYLES = {
  high: { text: "text-emerald-600", bg: "bg-emerald-500", border: "border-emerald-100", light: "bg-emerald-50" },
  mid:  { text: "text-amber-600",   bg: "bg-amber-500",   border: "border-amber-100",   light: "bg-amber-50"   },
  low:  { text: "text-rose-600",    bg: "bg-rose-500",    border: "border-rose-100",     light: "bg-rose-50"    },
};
function getScoreStyle(s) {
  if (s >= 70) return SCORE_STYLES.high;
  if (s >= 40) return SCORE_STYLES.mid;
  return SCORE_STYLES.low;
}

function fmtINR(v) {
  if (!v) return "—";
  if (v >= 10_000_000) return `₹${(v/10_000_000).toFixed(1)} Cr`;
  if (v >= 100_000) return `₹${(v/100_000).toFixed(1)}L`;
  return `₹${v.toLocaleString("en-IN")}`;
}

// ── Draft Modal ───────────────────────────────────────────────────────────────
function DraftModal({ draft, onClose }) {
  if (!draft) return null;
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <div className="text-sm font-black text-slate-900">{draft.title}</div>
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{draft.legal_basis}</div>
          </div>
          <button className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-500 transition-colors text-sm" onClick={onClose}>✕</button>
        </div>
        <div className="p-6 overflow-y-auto flex-1">
          <pre className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">{draft.text}</pre>
        </div>
        <div className="p-4 border-t border-slate-100 bg-slate-50 flex gap-3 justify-end">
          <button
            className="px-5 py-2.5 text-xs font-black uppercase tracking-widest bg-emerald-600 text-white rounded-xl hover:bg-emerald-500 transition-colors"
            onClick={() => navigator.clipboard.writeText(draft.text)}
          >📋 Copy Draft</button>
          <button className="px-4 py-2.5 text-xs font-black text-slate-400 hover:text-slate-600 transition-colors" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

// ── Main ADR Panel ────────────────────────────────────────────────────────────
export default function ADRPanel({ caseNumber, fullPage = false, overrideData = null }) {
  const [data, setData]         = useState(overrideData || null);
  const [loading, setLoading]   = useState(!overrideData);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draft, setDraft]       = useState(null);
  const [draftType, setDraftType] = useState("lok_adalat");
  const [error, setError]       = useState("");

  const abortRef = useRef(null);

  const fetchAssessment = useCallback(async () => {
    // ── Guard: skip if no caseNumber, overrideData present, or input is partial ──
    if (!caseNumber || overrideData || !isValidCaseNumberForFetch(caseNumber)) {
      setLoading(false);
      return;
    }

    // Cancel any previous in-flight request
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/adr/suitability/${encodeURIComponent(caseNumber)}`, {
        signal: abortRef.current.signal,
      });
      // 400 = partial/invalid input from backend validation
      // 404 = not assessed yet — silently ignore for panel mode
      if (res.status === 400 || res.status === 404) {
        setLoading(false);
        return;
      }
      if (res.ok) setData(await res.json());
    } catch (e) {
      if (e.name !== "AbortError") {
        // Swallow other network errors silently — backend may be starting up
      }
    } finally {
      setLoading(false);
    }
  }, [caseNumber, overrideData]);

  useEffect(() => { fetchAssessment(); }, [fetchAssessment]);

  const generateDraft = async () => {
    if (!caseNumber && !data) return;
    setDraftLoading(true);
    try {
      const res = await fetch(`${API}/adr/draft-application`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_number: caseNumber || "MANUAL",
          draft_type: draftType,
          case_details: "",
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Draft generation failed");
      const titles = {
        lok_adalat: "Lok Adalat Referral Application — Section 20 LSAA",
        arbitration_s8: "Section 8 Application — Arbitration & Conciliation Act",
        arbitration_s11: "Section 11 Petition — Appointment of Arbitrator",
      };
      setDraft({ title: titles[draftType], text: json.draft, legal_basis: json.legal_basis });
    } catch (e) { setError(e.message); }
    finally { setDraftLoading(false); }
  };

  if (loading) return <ADRSkeleton />;
  if (!data) return fullPage ? null : null;

  const pathways = [
    { key: "lok_adalat_score",  label: "Lok Adalat",  icon: "🏛️" },
    { key: "mediation_score",   label: "Mediation",   icon: "🤝" },
    { key: "arbitration_score", label: "Arbitration", icon: "⚖️" },
    { key: "negotiation_score", label: "Negotiation", icon: "💬" },
  ];

  const recommended = data.recommended_adr || "court";
  const confidence  = Math.round((data.confidence_level || 0) * 100);
  const recommendedCfg = getScoreStyle(data[`${recommended}_score`] || data.lok_adalat_score || 0);
  const factors = data.factors || [];

  return (
    <>
      <div className="bg-white border border-slate-200 rounded-3xl shadow-xl overflow-hidden transition-all duration-500 animate-in slide-in-from-bottom-6">
        {/* Header */}
        <div className="bg-slate-900 px-8 py-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-white/10 rounded-xl flex items-center justify-center text-xl border border-white/10">⚖️</div>
            <div>
              <div className="text-sm font-black text-white uppercase tracking-[0.2em]">ADR Suitability</div>
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">
                {data.case_type?.replace(/_/g, " ") || "Case"} · NALSA-informed scoring
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {data.is_lok_adalat_eligible && (
              <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-[9px] font-black uppercase tracking-widest border border-emerald-500/20">
                Lok Adalat Eligible
              </span>
            )}
            <span className="hidden sm:inline-block px-3 py-1 bg-white/10 text-slate-300 rounded-full text-[9px] font-black uppercase tracking-widest border border-white/10">
              {confidence}% confidence
            </span>
          </div>
        </div>

        <div className="p-8">
          {/* Pathway Scores */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10">
            {pathways.map(p => {
              const score = data[p.key] || 0;
              const cfg = getScoreStyle(score);
              const isRec = recommended === p.key.replace("_score", "");
              return (
                <div key={p.key} className={`p-5 rounded-2xl border transition-all duration-300 hover:shadow-md ${cfg.light} ${cfg.border} ${isRec ? "ring-2 ring-offset-2 ring-slate-400" : ""}`}>
                  <div className="flex justify-between items-start mb-3">
                    <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{p.label}</div>
                    <span className="text-base">{p.icon}</span>
                  </div>
                  <div className={`text-3xl font-black tabular-nums tracking-tighter mb-3 ${cfg.text}`}>{score}</div>
                  <div className="h-1.5 bg-white/60 rounded-full overflow-hidden">
                    <div className={`h-full transition-all duration-1000 ease-out ${cfg.bg}`} style={{ width: `${score}%` }} />
                  </div>
                  {isRec && <div className="text-[9px] font-black text-slate-500 uppercase tracking-widest mt-2">★ Recommended</div>}
                </div>
              );
            })}
          </div>

          {/* Recommendation block */}
          <div className={`rounded-2xl p-6 mb-8 border ${recommendedCfg.light} ${recommendedCfg.border} flex flex-col sm:flex-row items-center justify-between gap-6`}>
            <div>
              <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Recommended Pathway</div>
              <div className="text-3xl font-black text-slate-900 tracking-tight capitalize">{recommended.replace(/_/g," ")}</div>
              <div className="text-xs text-slate-400 font-semibold mt-1">{data.authority || "DLSA / SLSA"}</div>
            </div>
            <div className="flex flex-wrap gap-4 text-center">
              <div>
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Est. Settlement</div>
                <div className="text-2xl font-black text-slate-800">{data.settlement_range || fmtINR(data.predicted_settlement_amount)}</div>
                <div className="text-[9px] text-slate-400 uppercase font-bold">NALSA Band</div>
              </div>
              <div>
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Timeline</div>
                <div className="text-2xl font-black text-slate-800">{data.timeline_display || "—"}</div>
                <div className="text-[9px] text-slate-400 uppercase font-bold">Estimated</div>
              </div>
              <div>
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Closure</div>
                <div className={`text-2xl font-black ${recommendedCfg.text}`}>{data.settlement_pct_display || `${confidence}%`}</div>
                <div className="text-[9px] text-slate-400 uppercase font-bold">Likelihood</div>
              </div>
            </div>
          </div>

          {/* Factors + Risk */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
            <div>
              <h4 className="text-[10px] font-black text-emerald-600 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
                <span className="w-4 h-0.5 bg-emerald-500" /> Scoring Factors
              </h4>
              <div className="space-y-3">
                {factors.length > 0 ? factors.map((f, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-emerald-50/30 border border-emerald-50 rounded-xl">
                    <span className="text-emerald-500 font-black text-sm shrink-0">✓</span>
                    <div>
                      <div className="text-xs font-bold text-slate-700 capitalize">{String(f.name).replace(/_/g," ")}</div>
                      <div className="text-[10px] text-slate-400">{String(f.impact)}</div>
                    </div>
                  </div>
                )) : (
                  [{ label: "Case type suitability", icon: "📋" }, { label: "Party consent level", icon: "🤝" }, { label: "Dispute complexity", icon: "⚡" }].map((f, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-emerald-50/20 border border-emerald-50 rounded-xl">
                      <span>{f.icon}</span><span className="text-sm font-semibold text-slate-700">{f.label}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
            <div>
              <h4 className="text-[10px] font-black text-rose-600 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
                <span className="w-4 h-0.5 bg-rose-500" /> If ADR Rejected
              </h4>
              <div className="p-5 bg-rose-50/30 border border-rose-100 rounded-2xl">
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  {data.rejection_risk || "Rejecting ADR may significantly increase time and costs of resolution."}
                </p>
              </div>
            </div>
          </div>

          {/* Draft Application */}
          <div className="bg-slate-50 border border-slate-100 rounded-2xl p-6">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Auto-Generate Legal Application</div>
            <div className="flex flex-col sm:flex-row gap-3">
              <select
                className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-700 outline-none cursor-pointer focus:ring-4 focus:ring-slate-200 transition-all"
                value={draftType} onChange={e => setDraftType(e.target.value)}
              >
                <option value="lok_adalat">Lok Adalat Referral — Section 20 LSAA</option>
                <option value="arbitration_s8">Arbitration Reference — Section 8 A&C Act</option>
                <option value="arbitration_s11">Arbitrator Appointment — Section 11 A&C Act</option>
              </select>
              <button
                className="h-12 px-6 bg-slate-900 text-white rounded-xl text-xs font-black uppercase tracking-widest hover:bg-slate-800 active:scale-95 transition-all shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                onClick={generateDraft} disabled={draftLoading}
              >
                {draftLoading ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Drafting…</> : "📝 Generate Draft"}
              </button>
            </div>
            {error && <div className="mt-3 text-rose-600 text-xs font-bold p-3 bg-rose-50 rounded-xl">{error}</div>}
          </div>
        </div>
      </div>

      {draft && <DraftModal draft={draft} onClose={() => setDraft(null)} />}
    </>
  );
}

// ── Manual Assessment Form ────────────────────────────────────────────────────
export function ManualADRForm({ onResult }) {
  const CASE_TYPES = [
    { value: "motor_accident", label: "Motor Accident" },
    { value: "consumer",       label: "Consumer Dispute" },
    { value: "labour",         label: "Labour / Employment" },
    { value: "cheque_bounce",  label: "Cheque Bounce (NI Act 138)" },
    { value: "matrimonial",    label: "Matrimonial" },
    { value: "property",       label: "Property / Land" },
    { value: "commercial",     label: "Commercial / Contract" },
    { value: "civil",          label: "Civil / Other" },
  ];
  const CONSENT_OPTS = ["Both Willing","One Willing","Neutral","Unwilling"];

  const [form, setForm] = useState({
    case_type: "motor_accident",
    dispute_amount: "",
    dispute_years: "1",
    number_of_parties: "2",
    party_consent_level: "Neutral",
    case_description: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    setLoading(true); setError("");
    try {
      const body = {
        case_number: `MANUAL-${Date.now()}`,
        case_type: form.case_type,
        dispute_amount: form.dispute_amount ? parseInt(form.dispute_amount.replace(/,/g,"")) : null,
        dispute_years: parseFloat(form.dispute_years) || 1,
        number_of_parties: parseInt(form.number_of_parties) || 2,
        party_consent_level: form.party_consent_level,
        case_description: form.case_description,
      };
      const res = await fetch(`${API}/adr/assess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Assessment failed");
      onResult && onResult(json);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-3xl shadow-xl p-8">
      <div className="flex items-center gap-3 mb-8 pb-5 border-b border-slate-100">
        <div className="w-2 h-2 rounded-full bg-emerald-500" />
        <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-400">Manual Case Assessment</h3>
        <span className="ml-auto text-[10px] font-bold text-slate-300 uppercase tracking-widest">No upload needed</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-6">
        <div>
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Case Type</label>
          <select
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-bold text-slate-700 outline-none focus:ring-4 focus:ring-slate-200 transition-all cursor-pointer"
            value={form.case_type} onChange={e => set("case_type", e.target.value)}
          >
            {CASE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Dispute Amount (₹)</label>
          <input
            type="text" placeholder="e.g. 500000"
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-bold text-slate-700 outline-none focus:ring-4 focus:ring-slate-200 transition-all"
            value={form.dispute_amount} onChange={e => set("dispute_amount", e.target.value)}
          />
        </div>
        <div>
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Dispute Duration (years)</label>
          <input
            type="number" min="0" step="0.5"
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-bold text-slate-700 outline-none focus:ring-4 focus:ring-slate-200 transition-all"
            value={form.dispute_years} onChange={e => set("dispute_years", e.target.value)}
          />
        </div>
        <div>
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Number of Parties</label>
          <input
            type="number" min="2" max="10"
            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-bold text-slate-700 outline-none focus:ring-4 focus:ring-slate-200 transition-all"
            value={form.number_of_parties} onChange={e => set("number_of_parties", e.target.value)}
          />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Party Consent Level</label>
          <div className="flex flex-wrap gap-2">
            {CONSENT_OPTS.map(opt => (
              <button key={opt}
                className={`px-4 py-2 rounded-xl text-xs font-black border transition-all ${form.party_consent_level === opt ? "bg-slate-900 text-white border-slate-900" : "bg-slate-50 text-slate-400 border-slate-200 hover:border-slate-300"}`}
                onClick={() => set("party_consent_level", opt)}
              >{opt}</button>
            ))}
          </div>
        </div>
        <div className="sm:col-span-2">
          <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Case Description (optional)</label>
          <textarea
            className="w-full h-24 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm text-slate-700 outline-none focus:ring-4 focus:ring-slate-200 transition-all resize-none placeholder:text-slate-300"
            placeholder="Brief description for AI classification..."
            value={form.case_description} onChange={e => set("case_description", e.target.value)}
          />
        </div>
      </div>

      {error && <div className="mb-4 text-rose-600 text-xs font-bold p-3 bg-rose-50 rounded-xl border border-rose-100">{error}</div>}

      <button
        className="w-full h-12 bg-emerald-700 text-white rounded-xl text-xs font-black uppercase tracking-widest hover:bg-emerald-600 active:scale-[0.99] transition-all shadow-lg shadow-emerald-900/20 disabled:opacity-50 flex items-center justify-center gap-2"
        onClick={submit} disabled={loading}
      >
        {loading ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Running Assessment…</> : "⚡ Run ADR Assessment"}
      </button>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
function ADRSkeleton() {
  return (
    <div className="bg-white border border-slate-200 rounded-3xl p-8 animate-pulse shadow-sm">
      <div className="h-4 bg-slate-100 rounded w-1/4 mb-10" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[0,1,2,3].map(i => (
          <div key={i} className="bg-slate-50 border border-slate-100 p-5 rounded-2xl h-36 flex flex-col justify-between">
            <div className="h-2 bg-slate-200 rounded w-1/2" />
            <div className="h-8 bg-slate-200 rounded w-1/4" />
            <div className="h-1.5 bg-slate-200 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
