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
        <div className="pred-field">
            <label className="pred-label-text">{label}</label>
            {hint && <span className="pred-hint">{hint}</span>}
            {children}
        </div>
    );
}

function AnimatedBar({ pct, colorClass, label }) {
    return (
        <div className={`pred-side ${colorClass}`}>
            <div className="pred-label">{label}</div>
            <div className="pred-pct">{pct}%</div>
            <div className="pred-bar-wrap">
                <div
                    className={`pred-bar-fill ${colorClass === "plaintiff" ? "blue" : "red"}`}
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

    return (
        <div className="app-wrapper">
            {/* ── Nav ── */}
            <nav className="top-nav">
                <button className="nav-back" onClick={onBack}>← Back to Upload</button>
                <div className="nav-title">⚖ Predict Case Outcome</div>
            </nav>

            {/* ── Hero ── */}
            <div className="hero" style={{ paddingTop: 32 }}>
                <div className="hero-badge">🔮 Manual Prediction</div>
                <h1>Estimate Your <span className="accent">Chances</span></h1>
                <p>
                    Fill in case details below. The system uses weighted scoring based on<br />
                    thousands of past similar Indian court cases.
                </p>
            </div>

            {/* ── Form ── */}
            <div className="card pred-form-card">
                <div className="card-title"><span className="dot" />Case Details</div>

                <div className="pred-form-grid">
                    <FieldRow label="Case Type" hint="What kind of case is this?">
                        <select id="select-case-type" className="pred-select"
                            value={form.case_type} onChange={(e) => set("case_type", e.target.value)}>
                            {CASE_TYPES.map((t) => <option key={t}>{t}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Court Level" hint="Where is the case being heard?">
                        <select id="select-court-level" className="pred-select"
                            value={form.court_level} onChange={(e) => set("court_level", e.target.value)}>
                            {COURT_LEVELS.map((c) => <option key={c}>{c}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Dispute Type" hint="What is the main dispute about?">
                        <select id="select-dispute-type" className="pred-select"
                            value={form.dispute_type} onChange={(e) => set("dispute_type", e.target.value)}>
                            {DISPUTE_TYPES.map((d) => <option key={d}>{d}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Relief Sought" hint="What does the petitioner want from court?">
                        <select id="select-relief-type" className="pred-select"
                            value={form.relief_type} onChange={(e) => set("relief_type", e.target.value)}>
                            {RELIEF_TYPES.map((r) => <option key={r}>{r}</option>)}
                        </select>
                    </FieldRow>

                    <FieldRow label="Act / Law" hint="e.g. IPC, NI Act, CPC (optional)">
                        <input id="input-act" className="pred-input" type="text" placeholder="e.g. IPC"
                            value={form.act} onChange={(e) => set("act", e.target.value)} />
                    </FieldRow>

                    <FieldRow label="Section" hint="e.g. 138, 420, 302 (optional)">
                        <input id="input-section" className="pred-input" type="text" placeholder="e.g. 138"
                            value={form.section} onChange={(e) => set("section", e.target.value)} />
                    </FieldRow>
                </div>

                {/* Evidence Strength */}
                <FieldRow label="Evidence Strength" hint="How strong is the petitioner's evidence?">
                    <div className="evidence-options">
                        {EVIDENCE_OPTIONS.map((opt) => (
                            <button
                                key={opt.value}
                                id={`ev-${opt.value}`}
                                className={`evidence-btn${form.evidence_strength === opt.value ? " active" : ""}`}
                                onClick={() => set("evidence_strength", opt.value)}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>
                </FieldRow>

                {/* Delay toggle */}
                <FieldRow label="Was there a delay in filing?" hint="Filing after the allowed time limit weakens a case">
                    <div className="delay-toggle">
                        <button
                            id="delay-yes"
                            className={`delay-btn${form.delay_in_filing ? " active-red" : ""}`}
                            onClick={() => set("delay_in_filing", true)}
                        >
                            Yes — Filed Late
                        </button>
                        <button
                            id="delay-no"
                            className={`delay-btn${!form.delay_in_filing ? " active-green" : ""}`}
                            onClick={() => set("delay_in_filing", false)}
                        >
                            No — Filed On Time
                        </button>
                    </div>
                </FieldRow>

                {error && (
                    <div style={{ color: "var(--red)", background: "var(--red-soft)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 16px", fontSize: 13, marginBottom: 12 }}>
                        ⚠ {error}
                    </div>
                )}

                <button id="btn-predict-manual" className="btn btn-primary" style={{ width: "100%", padding: 16, fontSize: 16 }}
                    onClick={submit} disabled={loading}>
                    {loading ? <><span className="spinner" /> Calculating…</> : "🔮 Predict Outcome"}
                </button>
            </div>

            {/* ── Result ── */}
            {result && (
                <>
                    <div className="section-sep">Prediction Result</div>
                    <div className="card" style={{ animationDelay: "0.05s" }}>
                        <div className="card-title">
                            <span className="dot" style={{ background: "var(--gold)" }} />
                            {result.outcome}
                        </div>

                        <div className="prediction-grid">
                            <AnimatedBar pct={result.plaintiff_pct} colorClass="plaintiff" label="Petitioner / Plaintiff" />
                            <AnimatedBar pct={result.defendant_pct} colorClass="defendant" label="Respondent / Defendant" />
                        </div>

                        <div className="pred-outcome" style={{ marginTop: 16 }}>
                            {result.explanation}
                        </div>

                        {result.factors?.length > 0 && (
                            <div className="pred-factors">
                                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", margin: "14px 0 8px" }}>
                                    Factors Used
                                </div>
                                {result.factors.map((f, i) => (
                                    <div key={i} className="pred-factor">{f}</div>
                                ))}
                            </div>
                        )}

                        <div style={{ marginTop: 16, padding: "12px 16px", background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.15)", borderRadius: 8, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.7 }}>
                            ⚠ {result.disclaimer}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
