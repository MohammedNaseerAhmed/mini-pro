import { useState } from "react";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

const CASE_TYPES = [
    "Civil Suit", "Criminal Case", "Criminal Appeal", "Writ Petition",
    "Maintenance Case", "Bail Application", "Family Court Case",
    "Family Court Original Petition", "Appeal Suit", "Second Appeal",
    "Civil Miscellaneous Appeal", "Original Petition", "Execution Petition",
    "Land Acquisition Case", "Rent Control Case",
];

const COURT_LEVELS = [
    "Supreme Court", "High Court", "District Court", "Sessions Court",
    "Magistrate Court", "Family Court",
];

const DISPUTE_TYPES = [
    "Property Dispute", "Cheque Bounce", "Domestic Violence", "Maintenance",
    "Criminal", "Bail", "Service Matter", "Land Acquisition", "Motor Accident",
    "Consumer Dispute", "Divorce", "Custody", "Writ", "Contempt", "Defamation",
    "Injunction", "Recovery", "Insolvency", "Contract Breach", "Rent",
];

const EVIDENCE_OPTIONS = [
    { value: "strong", label: "💪 Strong — clear documents, witnesses, proof" },
    { value: "medium", label: "🟡 Medium — some evidence but gaps" },
    { value: "weak", label: "🔴 Weak — mostly allegations, no solid proof" },
];

const RELIEF_TYPES = [
    "Compensation", "Declaration", "Injunction", "Bail", "Quashing FIR",
    "Divorce", "Custody", "Maintenance", "Recovery", "Possession",
    "Specific Performance", "Mandamus", "Certiorari",
];

function FieldRow({ label, hint, children }) {
    return (
        <div className="form-group mb-6">
            <div className="flex flex-col gap-0.5">
                <label className="form-label">{label}</label>
                {hint && <span style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", opacity: 0.7 }}>{hint}</span>}
            </div>
            {children}
        </div>
    );
}

function AnimatedBar({ pct, colorClass, label }) {
    const isPlaintiff = colorClass === "plaintiff";
    return (
        <div className={`p-6 rounded-2xl border transition-all duration-300 shadow-sm ${
            isPlaintiff 
                ? "bg-blue-50 border-blue-100 text-blue-700" 
                : "bg-rose-50 border-rose-100 text-rose-700"
        }`}>
            <div className="text-[10px] font-black uppercase tracking-widest opacity-60 mb-2">{label}</div>
            <div className="text-4xl font-black tabular-nums tracking-tighter mb-4">{pct}%</div>
            <div className="h-2 bg-white/50 rounded-full overflow-hidden shadow-inner">
                <div
                    className={`h-full transition-all duration-1000 ease-out shadow-glow ${
                        isPlaintiff ? "bg-blue-500 shadow-blue-500/50" : "bg-rose-500 shadow-rose-500/50"
                    }`}
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    );
}

export default function PredictionPage({ onBack }) {
    const [form, setForm] = useState({
        case_type: "Civil Suit",
        court_level: "District Court",
        act: "",
        section: "",
        dispute_type: "Property Dispute",
        evidence_strength: "medium",
        delay_in_filing: false,
        relief_type: "Declaration",
    });
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const submit = async () => {
        setLoading(true);
        setError("");
        setResult(null);
        try {
            const res = await fetch(`${API_BASE}/predict/manual`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(form),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Prediction failed");
            setResult(data);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const inputStyles = "gold-select";

    return (
        <div className="max-w-5xl mx-auto px-6 py-12 pb-32">
            <nav className="flex items-center gap-4 mb-12">
                <button className="btn btn-ghost flex items-center gap-2" onClick={onBack}>
                    ← Back
                </button>
                <div className="h-6 w-px" style={{ background: "var(--border-gold)" }} />
                <div className="label-gold">Manual Inference Engine</div>
            </nav>

            <div className="bg-legal-900 text-white rounded-[2rem] p-10 sm:p-16 mb-12 shadow-2xl relative overflow-hidden animate-in fade-in duration-700">
                <div className="absolute top-0 right-0 w-80 h-80 bg-gold-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl" />
                <div className="relative z-10 space-y-6">
                    <div className="inline-flex items-center gap-2 bg-white/10 px-4 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border border-white/10">
                        🔮 Bayesian Scoring
                    </div>
                    <h1 className="text-4xl sm:text-6xl font-black tracking-tight leading-tight">
                        Predict Your <br /><span className="text-gold-400 italic">Legal Odds</span>
                    </h1>
                    <p className="text-slate-400 text-lg max-w-xl leading-relaxed">
                        Input procedural details to run a simulated legal outcome based on precedent patterns and legislative weights.
                    </p>
                </div>
            </div>

            <div className="glass-card p-8 sm:p-12 mb-12 animate-fade-up">
                <div className="flex items-center gap-3 mb-10 pb-6" style={{ borderBottom: "1px solid var(--border-gold)" }}>
                    <div className="w-2 h-2 rounded-full" style={{ background: "#C9A84C", boxShadow: "0 0 8px rgba(201,168,76,0.5)" }} />
                    <h3 className="label-xs">Constituent data</h3>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12">
                    <FieldRow label="Framework Case Type" hint="High-level classification">
                        <select id="select-case-type" className="gold-select"
                            value={form.case_type} onChange={(e) => set("case_type", e.target.value)}>
                            {CASE_TYPES.map((t) => <option key={t}>{t}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Judicial Tier" hint="Court level of hearing">
                        <select id="select-court-level" className="gold-select"
                            value={form.court_level} onChange={(e) => set("court_level", e.target.value)}>
                            {COURT_LEVELS.map((c) => <option key={c}>{c}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Primary Dispute" hint="Nature of contention">
                        <select id="select-dispute-type" className="gold-select"
                            value={form.dispute_type} onChange={(e) => set("dispute_type", e.target.value)}>
                            {DISPUTE_TYPES.map((d) => <option key={d}>{d}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Relief Directive" hint="Target legal outcome">
                        <select id="select-relief-type" className="gold-select"
                            value={form.relief_type} onChange={(e) => set("relief_type", e.target.value)}>
                            {RELIEF_TYPES.map((r) => <option key={r}>{r}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Governing Act" hint="Applicable legislative code">
                        <input id="input-act" className="gold-input" type="text" placeholder="e.g. IPC, NI Act"
                            value={form.act} onChange={(e) => set("act", e.target.value)} />
                    </FieldRow>

                    <FieldRow label="Statutory Section" hint="Specific provision">
                        <input id="input-section" className="gold-input" type="text" placeholder="e.g. 138, 420"
                            value={form.section} onChange={(e) => set("section", e.target.value)} />
                    </FieldRow>
                </div>

                <div className="mt-8 pt-10" style={{ borderTop: "1px solid var(--border-gold)" }}>
                    <FieldRow label="Evidentiary Strength" hint="Qualitative assessment of proof">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            {EVIDENCE_OPTIONS.map((opt) => (
                                <button
                                    key={opt.value}
                                    id={`ev-${opt.value}`}
                                    className={`px-4 py-4 rounded-xl text-left text-xs font-bold transition-all duration-200`}
                                    style={form.evidence_strength === opt.value
                                        ? { background: "rgba(201,168,76,0.15)", border: "1.5px solid rgba(201,168,76,0.55)", color: "#C9A84C" }
                                        : { background: "rgba(255,255,255,0.03)", border: "1.5px solid rgba(255,255,255,0.08)", color: "var(--text-secondary)" }}
                                    onClick={() => set("evidence_strength", opt.value)}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </FieldRow>

                    <FieldRow label="Procedural Timeliness" hint="Impact of filing delays">
                        <div className="flex gap-3">
                            <button
                                id="delay-yes"
                                className="flex-1 px-6 py-4 rounded-xl text-xs font-black uppercase tracking-widest transition-all duration-200"
                                style={form.delay_in_filing
                                    ? { background: "rgba(248,81,73,0.12)", border: "1.5px solid rgba(248,81,73,0.50)", color: "#fca5a5" }
                                    : { background: "rgba(255,255,255,0.03)", border: "1.5px solid rgba(255,255,255,0.08)", color: "var(--text-muted)", opacity: 0.55 }}
                                onClick={() => set("delay_in_filing", true)}
                            >
                                ⚠ Delayed Filing
                            </button>
                            <button
                                id="delay-no"
                                className="flex-1 px-6 py-4 rounded-xl text-xs font-black uppercase tracking-widest transition-all duration-200"
                                style={!form.delay_in_filing
                                    ? { background: "rgba(63,185,80,0.12)", border: "1.5px solid rgba(63,185,80,0.50)", color: "#86efac" }
                                    : { background: "rgba(255,255,255,0.03)", border: "1.5px solid rgba(255,255,255,0.08)", color: "var(--text-muted)", opacity: 0.55 }}
                                onClick={() => set("delay_in_filing", false)}
                            >
                                ✓ On Time
                            </button>
                        </div>
                    </FieldRow>
                </div>

                {error && (
                    <div className="mt-8 p-4 rounded-xl flex items-center gap-3 animate-fade-up"
                        style={{ background: "rgba(248,81,73,0.10)", border: "1px solid rgba(248,81,73,0.30)", color: "#fca5a5", fontSize: "0.875rem", fontWeight: 600 }}>
                        <span>⚠</span> {error}
                    </div>
                )}

                <button id="btn-predict-manual"
                    className="btn btn-primary mt-12 w-full h-14 text-base"
                    onClick={submit} disabled={loading}>
                    {loading ? (
                        <><span className="inline-block w-5 h-5 border-2 rounded-full animate-spin"
                            style={{ borderColor: "rgba(10,14,26,0.3)", borderTopColor: "#0A0E1A" }} />
                            Running Simulation…
                        </>
                    ) : "🔮 Generate Prediction"}
                </button>
            </div>

            {result && (
                <div className="animate-in slide-in-from-bottom-10 duration-700 fill-mode-both">
                    <div className="flex items-center gap-4 py-8">
                        <div className="flex-1 h-px bg-slate-200"></div>
                        <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-slate-400">Simulation Output</h2>
                        <div className="flex-1 h-px bg-slate-200"></div>
                    </div>

                    <div className="bg-white border border-slate-200 rounded-[2.5rem] shadow-2xl p-8 sm:p-16 relative overflow-hidden">
                        <div className="absolute top-0 right-0 p-12 opacity-5 pointer-events-none">
                            <div className="text-[12rem] font-black tracking-tighter">OS</div>
                        </div>
                        
                        <div className="flex items-center gap-4 mb-10">
                            <div className="w-12 h-1 bg-gold-500 rounded-full" />
                            <h3 className="text-2xl sm:text-4xl font-black text-legal-900 tracking-tight">
                                {result.outcome}
                            </h3>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
                            <AnimatedBar pct={result.plaintiff_pct} colorClass="plaintiff" label="Petitioner Win Probability" />
                            <AnimatedBar pct={result.defendant_pct} colorClass="defendant" label="Respondent Win Probability" />
                        </div>

                        <div className="bg-slate-50 border border-slate-100 rounded-3xl p-8 sm:p-10 text-lg text-slate-700 leading-relaxed font-medium mb-10">
                            {result.explanation}
                        </div>

                        {result.factors?.length > 0 && (
                            <div className="space-y-6">
                                <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 px-1">Risk & Merit Matrix</h4>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {result.factors.map((f, i) => (
                                        <div key={i} className="flex items-start gap-3 p-4 bg-white border border-slate-100 rounded-xl shadow-sm group hover:border-legal-200 transition-colors">
                                            <span className="text-gold-500 font-bold group-hover:scale-125 transition-transform shrink-0">→</span>
                                            <span className="text-sm font-semibold text-slate-600">{f}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mt-16 p-6 bg-slate-900 rounded-2xl flex flex-col sm:flex-row items-center gap-6">
                            <div className="w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center shrink-0 border border-white/10">
                                <span className="text-rose-400 text-2xl font-black">!</span>
                            </div>
                            <div className="text-[11px] font-medium text-slate-400 leading-relaxed uppercase tracking-wider">
                                <strong className="text-white">Heuristic Disclaimer:</strong> {result.disclaimer}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
