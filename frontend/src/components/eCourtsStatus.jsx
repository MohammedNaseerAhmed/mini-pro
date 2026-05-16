import { useState, useEffect, useCallback, useRef } from "react";

// ── Helpers ───────────────────────────────────────────────────────────────────
function timeSince(dateStr) {
  try {
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch { return ""; }
}

function fmtDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

// ── CNR / case-number client-side pre-validation ──────────────────────────────
function isValidCaseNumberForFetch(val) {
  if (!val) return false;
  const cleaned = val.replace(/[\s-]/g, "").toUpperCase();
  // Reject lone state-code fragments, very short strings, or obvious partials
  if (cleaned.length < 5) return false;
  // Must contain at least one digit (e.g. OS/131/2026 has digits, "OS" alone doesn't)
  if (!/\d/.test(cleaned)) return false;
  return true;
}

function UrgencyBadge({ urgency }) {
  if (!urgency || urgency.level === "unknown") return null;
  const styles = {
    critical: "bg-red-500 text-white border-red-600 animate-pulse",
    high:     "bg-amber-500 text-white border-amber-600",
    medium:   "bg-yellow-100 text-yellow-800 border-yellow-200",
    low:      "bg-emerald-100 text-emerald-700 border-emerald-200",
    past:     "bg-slate-100 text-slate-500 border-slate-200",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border ${styles[urgency.level] || styles.low}`}>
      {urgency.level === "critical" && <span>🚨</span>}
      {urgency.level === "high" && <span>⚠</span>}
      Next Hearing: {urgency.label}
    </span>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function eCourtsPanel({ caseNumber, cnrNumber, fullPage = false }) {
  const [data, setData]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [syncing, setSyncing]       = useState(false);
  const [captchaStep, setCaptchaStep] = useState(null); // null | "loading" | "ready"
  const [captchaImg, setCaptchaImg] = useState("");
  const [captchaCookies, setCaptchaCookies] = useState({});
  const [captchaInput, setCaptchaInput] = useState("");
  const [cnr, setCnr]               = useState(cnrNumber || "");
  const [syncedAgo, setSyncedAgo]   = useState(null);
  const [aiSummary, setAiSummary]   = useState("");
  const [activeTab, setActiveTab]   = useState("overview"); // overview | history | ai
  const [error, setError]           = useState("");

  const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

  const fetchStatus = useCallback(async () => {
    // ── Guard: skip API call if caseNumber is clearly invalid ──────────────
    if (!caseNumber || !isValidCaseNumberForFetch(caseNumber)) {
      setLoading(false);
      return;
    }

    setLoading(true);
    const controller = new AbortController();
    try {
      const res = await fetch(`${API}/ecourts/status/${encodeURIComponent(caseNumber)}`, {
        signal: controller.signal,
      });
      if (res.status === 400) {
        // Partial/invalid input — backend rejected. Show nothing.
        setLoading(false);
        return;
      }
      if (res.ok) {
        const d = await res.json();
        setData(d);
        if (d.last_synced_at) setSyncedAgo(timeSince(d.last_synced_at));
        if (d.ai_summary) setAiSummary(d.ai_summary);
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        // Swallow network errors silently — backend may be starting up
      }
    } finally {
      setLoading(false);
    }
    return () => controller.abort();
  }, [caseNumber, API]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // Step 1: Fetch CAPTCHA image — calls new session-based /ecourts/captcha
  const handleInitSync = async () => {
    setError("");
    setCaptchaStep("loading");
    try {
      // Use new production endpoint (/captcha uses requests.Session internally)
      const res = await fetch(`${API}/ecourts/captcha`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to reach eCourts server.");
      }
      const json = await res.json();
      if (!json.success) throw new Error(json.error || "CAPTCHA load failed.");
      setCaptchaImg(json.captcha_image);
      setCaptchaCookies(json.cookies || {});
      setCaptchaStep("ready");
    } catch (e) {
      setError(e.message);
      setCaptchaStep(null);
    }
  };

  // Refresh CAPTCHA without losing CNR state
  const handleRefreshCaptcha = async () => {
    setCaptchaInput("");
    setError("");
    setCaptchaStep("loading");
    try {
      const res = await fetch(`${API}/ecourts/captcha`);
      const json = await res.json();
      if (!json.success) throw new Error(json.error || "CAPTCHA refresh failed.");
      setCaptchaImg(json.captcha_image);
      setCaptchaCookies(json.cookies || {});
      setCaptchaStep("ready");
    } catch (e) {
      setError(e.message);
      setCaptchaStep(null);
    }
  };

  // Step 2: Submit CNR + CAPTCHA via POST JSON body (never URL params)
  const handleCaptchaSubmit = async () => {
    const cnrClean = cnr.trim().toUpperCase();
    const captchaClean = captchaInput.trim();

    // Client-side guards before hitting backend
    if (!cnrClean) {
      setError("Please enter a CNR number.");
      return;
    }
    if (!captchaClean || captchaClean.length < 4) {
      setError("Please enter the CAPTCHA code (at least 4 characters).");
      return;
    }

    setSyncing(true); setError("");
    try {
      // POST JSON body — never passes CNR in URL path
      const res = await fetch(`${API}/ecourts/live-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cnr_number:   cnrClean,
          captcha_code: captchaClean,
          cookies:      captchaCookies,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Search failed.");
      setData(json);
      setSyncedAgo("just now");
      if (json.ai_summary) setAiSummary(json.ai_summary);
      setCaptchaStep(null);
      setCaptchaInput("");
      setActiveTab("overview");
    } catch (e) {
      setError(e.message);
    }
    setSyncing(false);
  };

  if (loading) return <ECSkeleton />;
  if (!data && !fullPage) return null;

  const isMock = !data || data.source === "mock";
  const urgency = data?.urgency;
  const hearingHistory = data?.hearing_history || data?.payload?.hearing_history || [];

  const infoGrid = [
    { label: "CNR Number",       value: data?.cnr_number,       mono: true, accent: "cyan"  },
    { label: "Case Status",      value: data?.case_stage,       bold: true                  },
    { label: "Next Hearing",     value: fmtDate(data?.next_hearing_date), bold: true, accent: "amber" },
    { label: "Judicial Officer", value: data?.judge_assigned,   bold: true                  },
    { label: "Petitioner",       value: data?.petitioner_name,  bold: true                  },
    { label: "Respondent",       value: data?.respondent_name,  bold: true                  },
    { label: "Court Complex",    value: data?.court_complex,    bold: true                  },
    { label: "Last Synced",      value: syncedAgo ? `${syncedAgo}` : "—" },
  ].filter(r => r.value && r.value !== "—");

  return (
    <div className="glass-card overflow-hidden animate-fade-up">
      {/* Header */}
      <div className="px-8 py-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4" style={{background:"rgba(5,8,15,0.7)",borderBottom:"1px solid var(--border-gold)"}}>
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl" style={{background:"rgba(201,168,76,0.12)",border:"1px solid rgba(201,168,76,0.30)"}}>🏛️</div>
          <div>
            <div className="text-sm font-black uppercase tracking-[0.2em]" style={{color:"var(--text-primary)"}}>eCourts Live Sync</div>
            <div className="text-[10px] font-bold uppercase tracking-widest mt-0.5" style={{color:"#C9A84C"}}>National Judicial Data Grid · NJDG Interface</div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {urgency && <UrgencyBadge urgency={urgency} />}
          <span className={`px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border ${
            isMock
              ? "bg-slate-500/20 text-slate-400 border-slate-500/20"
              : "bg-emerald-500/20 text-emerald-400 border-emerald-500/20"
          }`}>
            {isMock ? "No Live Data" : syncedAgo ? `Synced ${syncedAgo}` : "Live Data"}
          </span>
        </div>
      </div>

      {/* Tab Bar */}
      {data && (
        <div className="flex px-8" style={{borderBottom:"1px solid var(--border-gold)",background:"rgba(5,8,15,0.4)"}}>
          {[
            { id: "overview", label: "📋 Overview" },
            { id: "history",  label: `📅 Hearings${hearingHistory.length ? ` (${hearingHistory.length})` : ""}` },
            { id: "ai",       label: "🤖 AI Summary" },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="px-5 py-3.5 text-[11px] font-black uppercase tracking-widest transition-colors border-b-2 -mb-px"
              style={activeTab===tab.id
                ?{borderColor:"#C9A84C",color:"#C9A84C"}
                :{borderColor:"transparent",color:"var(--text-muted)"}}
            >{tab.label}</button>
          ))}
        </div>
      )}

      <div className="p-8">
        {/* Info / warning banners */}
        {isMock && (
          <div className="rounded-2xl p-4 mb-8 flex items-start gap-4" style={{background:"rgba(227,179,65,0.07)",border:"1px solid rgba(227,179,65,0.22)"}}>
            <span className="text-xl">ℹ️</span>
            <div className="text-xs font-semibold leading-relaxed" style={{color:"rgba(227,179,65,0.85)"}}>No live data found. Use <strong>Sync from eCourts</strong> below to fetch real-time case status. You'll need to solve a CAPTCHA from the eCourts portal.</div>
          </div>
        )}

        {error && (
          <div className="rounded-2xl p-4 mb-6 flex items-center gap-3 animate-fade-up" style={{background:"rgba(248,81,73,0.10)",border:"1px solid rgba(248,81,73,0.30)"}}>
            <span className="text-xl">⚠️</span>
            <span className="text-xs font-bold" style={{color:"#fca5a5"}}>{error}</span>
          </div>
        )}

        {/* CAPTCHA Flow */}
        {captchaStep && (
          <div className="bg-slate-900 rounded-2xl p-6 mb-8 animate-in zoom-in-95 duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="text-[10px] font-black text-cyan-400 uppercase tracking-widest">eCourts Live Search</div>
              <button className="text-slate-500 hover:text-slate-300 text-xs font-bold transition-colors"
                onClick={() => { setCaptchaStep(null); setError(""); }}>✕ Cancel</button>
            </div>

            {captchaStep === "loading" && (
              <div className="flex items-center gap-3 text-slate-400 py-4">
                <div className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                <span className="text-xs">Connecting to eCourts portal…</span>
              </div>
            )}

            {captchaStep === "ready" && (
              <div className="space-y-5">
                {/* CNR Input */}
                <div className="space-y-1.5">
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                    CNR Number <span className="text-cyan-400">*</span>
                  </label>
                  <input
                    className="gold-input"
                    style={{fontFamily:"'IBM Plex Mono',monospace",fontWeight:700}}
                    placeholder="e.g. MHPN010101234562021"
                    value={cnr}
                    onChange={e => setCnr(e.target.value.toUpperCase())}
                    maxLength={20}
                  />
                  {cnr && cnr.replace(/[\s-]/g,"").length < 8 && (
                    <p className="text-[10px] text-amber-400 font-bold">Enter the full CNR number (16 characters)</p>
                  )}
                </div>

                {/* CAPTCHA Image + Refresh */}
                <div className="space-y-1.5">
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                    CAPTCHA Image
                  </label>
                  <div className="flex items-center gap-3">
                    <img src={captchaImg} alt="CAPTCHA" className="h-12 rounded-lg border border-slate-700 bg-white px-2 py-1" />
                    <button
                      onClick={handleRefreshCaptcha}
                      className="px-3 py-2 text-[10px] font-black text-slate-400 hover:text-cyan-400 border border-slate-700 rounded-lg uppercase tracking-widest transition-colors"
                      title="Get a new CAPTCHA"
                    >🔄 Refresh</button>
                  </div>
                </div>

                {/* CAPTCHA Input + Submit */}
                <div className="flex gap-3">
                  <input
                    className="gold-input"
                    style={{flex:1,fontFamily:"'IBM Plex Mono',monospace",fontWeight:700}}
                    placeholder="Type CAPTCHA here…"
                    value={captchaInput}
                    onChange={e => setCaptchaInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleCaptchaSubmit()}
                    autoFocus
                  />
                  <button
                    className="btn btn-primary px-6 whitespace-nowrap"
                    onClick={handleCaptchaSubmit}
                    disabled={syncing || cnr.replace(/[\s-]/g,"").length < 8 || captchaInput.trim().length < 4}
                  >
                    {syncing
                      ? <><span className="inline-block w-4 h-4 border-2 rounded-full animate-spin" style={{borderColor:"rgba(10,14,26,0.3)",borderTopColor:"#0A0E1A"}} />Searching…</>
                      : "🔍 Search"}
                  </button>
                </div>

                <p className="text-[10px] text-slate-500 leading-relaxed">
                  Enter the text shown in the image above. Click 🔄 to get a new CAPTCHA if unclear.
                  Your data is sent directly to eCourts — no intermediate processing.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Tab: Overview */}
        {(!data || activeTab === "overview") && (
          <>
            {(!data?.cnr_number) && (
              <div className="mb-8">
                <label className="form-label mb-2 ml-1">CNR Number (16-digit)</label>
                <input
                  className="gold-input"
                  style={{fontFamily:"'IBM Plex Mono',monospace",fontWeight:700}}
                  value={cnr}
                  onChange={e => setCnr(e.target.value)}
                  placeholder="Enter 16-digit CNR Number..."
                />
              </div>
            )}

            {infoGrid.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-px rounded-2xl overflow-hidden mb-8" style={{background:"var(--border-gold)",border:"1px solid var(--border-gold)"}}>
                {infoGrid.map(({ label, value, mono, bold, accent }, i) => (
                  <div key={i} className="p-5" style={{background:"var(--bg-elevated)"}}>
                    <div className="label-xs mb-2">{label}</div>
                    <div className={`text-sm tracking-tight ${bold?"font-black":"font-medium"} ${mono?"font-mono":""} ${accent==="cyan"?"text-cyan-400":accent==="amber"?"text-amber-400":""}`}
                      style={!accent||accent==="none"?{color:"var(--text-primary)"}:{}}>{value}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Tab: Hearing History */}
        {activeTab === "history" && (
          <div>
            {hearingHistory.length > 0 ? (
              <div className="overflow-hidden rounded-2xl" style={{border:"1px solid var(--border-gold)"}}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr style={{background:"rgba(5,8,15,0.6)",borderBottom:"1px solid var(--border-gold)"}}>
                      <th className="px-5 py-3.5 label-xs">#</th>
                      <th className="px-5 py-3.5 label-xs">Date</th>
                      <th className="px-5 py-3.5 label-xs">Purpose</th>
                      <th className="px-5 py-3.5 label-xs">Business</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hearingHistory.map((h, i) => (
                      <tr key={i} style={{borderBottom:"1px solid rgba(255,255,255,0.04)"}} onMouseEnter={e=>e.currentTarget.style.background="rgba(255,255,255,0.02)"} onMouseLeave={e=>e.currentTarget.style.background=""}>
                        <td className="px-5 py-4 text-xs font-bold" style={{color:"var(--text-muted)"}}>{i+1}</td>
                        <td className="px-5 py-4 text-xs font-mono font-bold" style={{color:"var(--text-primary)"}}>{h.date||"—"}</td>
                        <td className="px-5 py-4 text-xs" style={{color:"var(--text-secondary)"}}>{h.purpose||"—"}</td>
                        <td className="px-5 py-4 text-xs" style={{color:"var(--text-muted)"}}>{h.business||"—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-16 text-center rounded-2xl" style={{border:"2px dashed var(--border-gold)"}}>
                <div className="text-4xl mb-3 opacity-30">📅</div>
                <p className="text-sm font-semibold" style={{color:"var(--text-muted)"}}>No hearing history available.</p>
                <p className="text-xs mt-1" style={{color:"var(--text-muted)",opacity:0.6}}>Sync from eCourts to load the full hearing calendar.</p>
              </div>
            )}
          </div>
        )}

        {/* Tab: AI Summary */}
        {activeTab === "ai" && (
          <div>
            {aiSummary ? (
              <div className="bg-gradient-to-br from-cyan-950 to-slate-900 rounded-2xl p-8 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none text-[10rem] font-black text-white">AI</div>
                <div className="text-[10px] font-black text-cyan-400 uppercase tracking-widest mb-4">AI Case Intelligence</div>
                <p className="text-white/90 text-base leading-relaxed font-medium">{aiSummary}</p>
                {urgency?.level === "critical" && (
                  <div className="mt-6 p-4 bg-red-500/20 border border-red-500/30 rounded-xl">
                    <div className="text-red-400 font-black text-sm">🚨 Urgent: {urgency.label}</div>
                    <div className="text-red-300 text-xs mt-1">Immediate action required — prepare case documents.</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-16 text-center rounded-2xl" style={{border:"2px dashed var(--border-gold)"}}>
                <div className="text-4xl mb-3 opacity-30">🤖</div>
                <p className="text-sm font-semibold" style={{color:"var(--text-muted)"}}>No AI summary yet.</p>
                <p className="text-xs mt-1" style={{color:"var(--text-muted)",opacity:0.6}}>Sync from eCourts to generate an AI-powered case brief.</p>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center gap-4 mt-8 pt-6" style={{borderTop:"1px solid var(--border-gold)"}}>
          {!captchaStep && (
            <button
              className="btn btn-primary w-full sm:w-auto h-12 px-8 gap-3"
              onClick={handleInitSync}
              disabled={syncing || captchaStep}
            >
              <span>↻</span> Sync from eCourts
            </button>
          )}
          {data && (
            <button
              className="btn btn-ghost w-full sm:w-auto h-12 px-6 gap-2"
              onClick={fetchStatus}
            >
              <span>🔄</span> Refresh Stored Data
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
function ECSkeleton() {
  return (
    <div className="glass-card p-8 animate-pulse">
      <div className="h-4 rounded w-1/4 mb-10" style={{background:"rgba(255,255,255,0.06)"}} />
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        {[0,1,2,3,4,5,6,7].map(i => (
          <div key={i} className="h-20 rounded-2xl p-4 flex flex-col justify-between" style={{background:"rgba(255,255,255,0.04)",border:"1px solid var(--border-subtle)"}}>
            <div className="h-1.5 rounded w-1/2" style={{background:"rgba(255,255,255,0.07)"}} />
            <div className="h-3 rounded w-3/4" style={{background:"rgba(255,255,255,0.07)"}} />
          </div>
        ))}
      </div>
    </div>
  );
}
