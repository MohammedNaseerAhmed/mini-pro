import { useState, useEffect } from "react";
import "./styles.css";
import UploadZone from "./components/UploadZone";
import RecentCasesPanel from "./components/RecentCasesPanel";
import Chatbot from "./components/Chatbot";
import PredictionPage from "./components/PredictionPage";

// ─── API helper ────────────────────────────────────────────────────────────────
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

async function api(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options || {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || `HTTP ${res.status}`);
  return data;
}

// ─── Hash-based Router ────────────────────────────────────────────────────────
function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onHash = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash;
}

// ─── Top Navigation Bar ───────────────────────────────────────────────────────
function NavBar({ active }) {
  return (
    <nav className="top-nav">
      <div className="nav-brand">⚖ Legal AI</div>
      <div className="nav-links">
        <a href="#/" className={`nav-link${active === "#/" ? " active" : ""}`}>📤 Upload & Analyze</a>
        <a href="#/predict" className={`nav-link${active === "#/predict" ? " active" : ""}`}>🔮 Predict Outcome</a>
      </div>
    </nav>
  );
}

// ─── Case Metadata Card ───────────────────────────────────────────────────────
function CaseMetaCard({ meta }) {
  if (!meta) return null;
  const fields = [
    { label: "Case Number", value: meta.case_number, color: "var(--gold)" },
    { label: "Case Type", value: meta.case_type },
    { label: "Year", value: meta.case_year },
    { label: "Court", value: meta.court_name },
    { label: "Court Level", value: meta.court_level },
    { label: "Judge", value: meta.judge_name },
    { label: "Petitioner", value: meta.petitioner },
    { label: "Respondent", value: meta.respondent },
  ].filter((f) => f.value && f.value !== "unknown");

  if (fields.length === 0) return null;

  return (
    <div className="card" style={{ animationDelay: "0.1s" }}>
      <div className="card-title">
        <span className="dot" style={{ background: "var(--gold)" }} />Extracted Case Information
      </div>
      <div className="meta-grid">
        {fields.map((f) => (
          <div key={f.label} className="meta-field">
            <span className="meta-field-label">{f.label}</span>
            <span className="meta-field-value" style={f.color ? { color: f.color, fontFamily: "monospace" } : {}}>
              {f.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Stateless display panels ─────────────────────────────────────────────────

function MetaBar({ uploadData }) {
  if (!uploadData) return null;
  const langMap = { en: "🇬🇧 English", hi: "🇮🇳 Hindi", te: "🇮🇳 Telugu", ur: "🇵🇰 Urdu" };
  return (
    <div className="meta-bar">
      <span className="meta-pill case-id">📋 {uploadData.case_number}</span>
      {uploadData.language_code && (
        <span className="meta-pill lang">{langMap[uploadData.language_code] || uploadData.language_code}</span>
      )}
      {uploadData.paragraph_count > 0 && (
        <span className="meta-pill paras">📄 {uploadData.paragraph_count} paragraphs</span>
      )}
      <span className="meta-pill status">✅ Stored & Ready</span>
    </div>
  );
}

function ActionBar({ caseNumber, onSummarize, onSimilar, loading }) {
  return (
    <div className="card">
      <div className="card-title">
        <span className="dot" style={{ background: "var(--blue)" }} />Run Analysis
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
        Click to analyse the uploaded document. Results appear below.
      </p>
      <div className="action-row">
        <button id="btn-summarize" className="btn btn-blue" onClick={onSummarize}
          disabled={!caseNumber || loading.summarize}>
          {loading.summarize ? <span className="spinner" /> : "📋"} Summarize
        </button>
        <button id="btn-similar" className="btn btn-purple" onClick={onSimilar}
          disabled={!caseNumber || loading.similar}>
          {loading.similar ? <span className="spinner" /> : "🔍"} Find Similar Cases
        </button>
        <a href="#/predict" className="btn btn-green" style={{ textDecoration: "none" }}>
          🔮 Predict Outcome →
        </a>
      </div>
    </div>
  );
}

function SummaryPanel({ data, caseNumber, language, setLanguage, onTranslate, loading, translation }) {
  const s = data?.summary || {};
  const langOptions = [
    { code: "hi", label: "🇮🇳 Hindi" },
    { code: "te", label: "🇮🇳 Telugu" },
    { code: "kn", label: "🇮🇳 Kannada" },
    { code: "ta", label: "🇮🇳 Tamil" },
    { code: "ml", label: "🇮🇳 Malayalam" },
    { code: "mr", label: "🇮🇳 Marathi" },
    { code: "simple_en", label: "🔤 Simple English" },
  ];
  if (!data && !loading.summarize) return null;
  return (
    <>
      <div className="section-sep">Case in Simple Words</div>
      {loading.summarize && (
        <div className="card"><div className="empty-state">
          <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
        </div></div>
      )}
      {(s.short_summary || s.basic_summary) && (
        <div className="card" style={{ animationDelay: "0.1s" }}>
          <div className="card-title"><span className="dot" />Quick Summary</div>
          {s.basic_summary && (
            <div className="summary-basic">{s.basic_summary}</div>
          )}
          {s.short_summary && !s.basic_summary && (
            <div className="summary-short">{s.short_summary}</div>
          )}
          {s.key_points?.length > 0 && (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10, marginTop: 16 }}>
                Key Points
              </div>
              <ul className="summary-key-points">
                {s.key_points.map((pt, i) => (
                  <li key={i}>
                    <span className="kp-num">{i + 1}</span>
                    <span>
                      {typeof pt === "object" && pt !== null
                        ? <><strong>{pt.label}:</strong> {pt.explanation}</>
                        : pt}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      {caseNumber && (
        <div className="card" style={{ animationDelay: "0.15s" }}>
          <div className="card-title">
            <span className="dot" style={{ background: "var(--cyan)" }} />Read in Your Language
          </div>
          {/* Language selector */}
          <div className="lang-tabs">
            {langOptions.map((l) => (
              <button key={l.code} id={`lang-tab-${l.code}`}
                className={`lang-tab${language === l.code ? " active" : ""}`}
                onClick={() => setLanguage(l.code)}>{l.label}
              </button>
            ))}
          </div>
          {/* Two translate buttons */}
          <div className="translate-row">
            <button id="btn-translate-summary" className="btn btn-ghost" onClick={() => onTranslate("summary")}
              disabled={loading.translate} title="Translate the plain-language summary">
              {loading.translate ? <span className="spinner" /> : "📋"} Translate Summary
            </button>
            <button id="btn-translate-raw" className="btn btn-ghost" onClick={() => onTranslate("raw")}
              disabled={loading.translate} title="Translate the full document text (may take a moment)">
              {loading.translate ? <span className="spinner" /> : "📄"} Translate Full Document
            </button>
          </div>
          {/* Translation result */}
          {translation && (
            <>
              {translation.error && (
                <div style={{
                  color: "var(--red)", background: "var(--red-soft)",
                  border: "1px solid rgba(239,68,68,0.25)",
                  borderRadius: 8, padding: "10px 14px", fontSize: 13, marginBottom: 10
                }}>
                  ⚠ Translation error: {translation.error}
                </div>
              )}
              {!translation.error && (
                <>
                  {translation.language_name && (
                    <div style={{ fontSize: 11, color: "var(--cyan)", fontWeight: 700, marginBottom: 6, textTransform: "uppercase" }}>
                      {translation.language_name} — {translation.mode === "raw" ? "Full Document" : "Summary"}
                    </div>
                  )}
                  <div className="translation-text">{translation.translated_text}</div>
                  {translation.model_used && <div className="model-badge">🤖 {translation.model_used}</div>}
                </>
              )}
            </>
          )}
          {!translation && !loading.translate && (
            <div style={{ fontSize: 13, color: "var(--text-dim)" }}>Select a language and click one of the Translate buttons above.</div>
          )}
        </div>
      )}
      {(s.short_summary || s.basic_summary) && (
        <div className="advice-box">
          <strong>📌 Neutral Guidance:</strong> This is an educational explanation only — not legal advice. If you are involved in this case, please consult a registered advocate.
        </div>
      )}
    </>
  );
}

// ─── Case Viewer Modal ────────────────────────────────────────────────────────
function CaseViewer({ caseData, onClose }) {
  if (!caseData) return null;
  const meta = caseData.case_metadata || {};
  const sum = caseData.summary || {};
  const fields = [
    { label: "Case Number", value: caseData.case_number },
    { label: "Case Type", value: meta.case_type },
    { label: "Year", value: meta.case_year },
    { label: "Court", value: meta.court_name },
    { label: "Court Level", value: meta.court_level },
    { label: "Judge", value: meta.judge_name },
    { label: "Petitioner", value: meta.petitioner },
    { label: "Respondent", value: meta.respondent },
  ].filter((f) => f.value && f.value !== "unknown");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕ Close</button>
        <div className="card-title" style={{ marginBottom: 16 }}>
          <span className="dot" style={{ background: "var(--gold)" }} />
          Similar Case — {caseData.case_number || "Unknown"}
        </div>
        {fields.length > 0 && (
          <div className="meta-grid" style={{ marginBottom: 16 }}>
            {fields.map((f) => (
              <div key={f.label} className="meta-field">
                <span className="meta-field-label">{f.label}</span>
                <span className="meta-field-value">{f.value}</span>
              </div>
            ))}
          </div>
        )}
        {sum.basic_summary && (
          <>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Summary</div>
            <div className="summary-basic">{sum.basic_summary}</div>
          </>
        )}
        {sum.key_points?.length > 0 && (
          <>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8, marginTop: 14 }}>Key Points</div>
            <ul className="summary-key-points">
              {sum.key_points.map((pt, i) => (
                <li key={i}>
                  <span className="kp-num">{i + 1}</span>
                  <span>
                    {typeof pt === "object" && pt !== null
                      ? <><strong>{pt.label}:</strong> {pt.explanation}</>
                      : pt}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        {!sum.basic_summary && !sum.key_points?.length && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>No summary stored. Run Summarize on this case first.</div>
        )}
      </div>
    </div>
  );
}

function SimilarCasesPanel({ data, loading, onCaseClick }) {
  if (!data && !loading.similar) return null;
  const kws = data?.keywords || [];
  const cases = data?.similar_cases || [];
  return (
    <>
      <div className="section-sep">Similar Past Cases</div>
      {loading.similar && (
        <div className="card"><div className="empty-state">
          <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
        </div></div>
      )}
      {kws.length > 0 && (
        <div className="card" style={{ animationDelay: "0.1s" }}>
          <div className="card-title">
            <span className="dot" style={{ background: "var(--blue)" }} />Detected Sections & Acts
          </div>
          <div className="kw-source">
            {kws.map((k, i) => <span key={i} className="kw-source-tag">{k}</span>)}
          </div>
        </div>
      )}
      {cases.length > 0 && (
        <div className="card" style={{ animationDelay: "0.15s" }}>
          <div className="card-title">
            <span className="dot" style={{ background: "var(--purple)" }} />Top {cases.length} Similar Cases
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>— click to view details</span>
          </div>
          {cases.map((c, i) => (
            <div
              key={c.case_number || i}
              className="similar-card clickable"
              onClick={() => onCaseClick && c.case_id && onCaseClick(c.case_id)}
              title={c.case_id ? "Click to view case details" : "No case ID"}
            >
              <div className="similar-card-header">
                <span className="similar-case-id">{c.case_number}</span>
                <span className="similar-case-title">{c.title || "—"}</span>
                <span className="score-badge">{Math.round((c.similarity_score || 0) * 100)}%</span>
                {c.case_id && <span className="view-btn">View →</span>}
              </div>
              <div className="score-bar-wrap">
                <div className="score-bar-fill" style={{ width: `${Math.round((c.similarity_score || 0) * 100)}%` }} />
              </div>
              {c.matched_keywords?.length > 0 && (
                <div className="kw-tags">
                  {c.matched_keywords.map((k, j) => <span key={j} className="kw-tag">{k}</span>)}
                </div>
              )}
              {(c.court || c.case_type) && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 12 }}>
                  {c.court && <span>🏛 {c.court}</span>}
                  {c.case_type && <span>📂 {c.case_type}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {data && !loading.similar && cases.length === 0 && (
        <div className="card">
          <div className="empty-state">
            <span className="es-icon">🔍</span>No similar cases found yet. Upload more documents to improve matching.
          </div>
        </div>
      )}
    </>
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
  const setErr = (k, v) => setErrors((e) => ({ ...e, [k]: v }));

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
    try {
      const data = await api(`/ai/case/${encodeURIComponent(caseId)}`);
      setViewedCase(data);
    } catch (e) {
      setErr("similar", `Could not load case: ${e.message}`);
    } finally {
      setLoad("viewCase", false);
    }
  };

  return (
    <div className="app-wrapper">
      <div className="hero">
        <div className="hero-badge">⚖ Legal AI for Citizens</div>
        <h1>Understand Any<br /><span className="accent">Court Document</span></h1>
        <p>Upload a petition, FIR, notice, or judgment — get a plain-language explanation in your language.</p>
      </div>

      <UploadZone onUploaded={handleUploaded} api={api} />
      <MetaBar uploadData={uploadData} />

      {/* Extracted metadata card */}
      {uploadData?.case_metadata && <CaseMetaCard meta={uploadData.case_metadata} />}

      {caseNumber && (
        <ActionBar caseNumber={caseNumber} onSummarize={doSummarize} onSimilar={doSimilar} loading={loading} />
      )}

      <SummaryPanel
        data={summary} caseNumber={caseNumber}
        language={language} setLanguage={setLanguage}
        onTranslate={doTranslate} loading={loading} translation={translation}
      />
      <SimilarCasesPanel data={similar} loading={loading} onCaseClick={doViewCase} />

      {/* Case viewer modal */}
      {(loading.viewCase || viewedCase) && (
        <CaseViewer
          caseData={loading.viewCase ? null : viewedCase}
          onClose={() => setViewedCase(null)}
        />
      )}

      {Object.entries(errors).map(([k, v]) => v ? (
        <div key={k} style={{ color: "var(--red)", background: "var(--red-soft)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "10px 16px", fontSize: 13, marginBottom: 12 }}>
          ⚠ {k}: {v}
        </div>
      ) : null)}

      <div className="section-sep">Case History</div>
      <RecentCasesPanel api={api} />
      <Chatbot api={api} />
    </div>
  );
}

// ─── Root App with hash routing ────────────────────────────────────────────────
export default function App() {
  const hash = useHash();
  const page = hash.replace("#", "").replace(/^\//, "") || "/";

  return (
    <>
      <NavBar active={hash.startsWith("#/predict") ? "#/predict" : "#/"} />
      {page === "predict"
        ? <PredictionPage onBack={() => { window.location.hash = "#/"; }} />
        : <UploadPage />
      }
    </>
  );
}
