import { useState, useEffect } from "react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// ── Feature routing map (which tables each feature uses) ─────────────────────
const FEATURES = [
  {
    id: "bns",      icon: "📖", label: "BNS Mapper",
    color: "amber",
    tables: ["section_mapping", "sections", "section_mapping_feedback"],
    href: "#/bns",
    apiCheck: "/intelligence/bns/search?q=murder",
  },
  {
    id: "predict",  icon: "🔮", label: "Predict Outcome",
    color: "purple",
    tables: ["case_facts", "case_predictions", "judge_analytics", "similar_cases"],
    href: "#/predict",
  },
  {
    id: "adr",      icon: "⚖️", label: "ADR Checker",
    color: "emerald",
    tables: ["adr_suitability", "lok_adalat_awards", "case_facts"],
    href: "#/adr",
  },
  {
    id: "ecourts",  icon: "🏛️", label: "eCourts Sync",
    color: "cyan",
    tables: ["ecourts_case_status", "ecourts_sync_log"],
    href: "#/ecourts",
  },
  {
    id: "summary",  icon: "📋", label: "Case Summaries",
    color: "blue",
    tables: ["case_facts", "case_summaries"],
    href: "#/",
  },
  {
    id: "similar",  icon: "🔍", label: "Similar Cases",
    color: "rose",
    tables: ["similar_cases", "case_section_citations", "case_facts"],
    href: "#/",
  },
  {
    id: "reports",  icon: "📑", label: "Legal Reports",
    color: "indigo",
    tables: ["case_section_reports", "sections", "case_acts"],
    href: "#/bns",
  },
  {
    id: "chat",     icon: "💬", label: "Chat Assistant",
    color: "teal",
    tables: ["chat_history", "cases", "sections"],
    href: "#/",
  },
];

// ── Table stat definitions ────────────────────────────────────────────────────
const TABLE_STATS = [
  { key: "sections_in_db",            label: "Legal Sections",       icon: "§",   color: "amber"   },
  { key: "section_mappings",          label: "Act Mappings",         icon: "↔",   color: "amber"   },
  { key: "total_cases",              label: "Cases Indexed",         icon: "🗂",  color: "blue"    },
  { key: "ecourts_cached",           label: "eCourts Cached",        icon: "🏛",  color: "cyan"    },
  { key: "adr_assessed",             label: "ADR Assessed",          icon: "⚖",   color: "emerald" },
  { key: "lok_adalat_eligible",      label: "Lok Adalat Eligible",   icon: "✓",   color: "emerald" },
  { key: "lok_adalat_awards",        label: "Lok Adalat Awards",     icon: "🏅",  color: "emerald" },
  { key: "predictions_stored",       label: "AI Predictions",        icon: "🔮",  color: "purple"  },
  { key: "summaries_stored",         label: "Summaries Stored",      icon: "📋",  color: "blue"    },
  { key: "similar_pairs",            label: "Similarity Pairs",      icon: "🔍",  color: "rose"    },
  { key: "deprecated_citation_cases",label: "Deprecated Citations",  icon: "⚠",   color: "rose"    },
  { key: "sync_log_entries",         label: "Sync Log Entries",      icon: "📡",  color: "slate"   },
];

const COLOR = {
  amber:   "bg-amber-50   border-amber-100  text-amber-700",
  blue:    "bg-blue-50    border-blue-100   text-blue-700",
  cyan:    "bg-cyan-50    border-cyan-100   text-cyan-700",
  emerald: "bg-emerald-50 border-emerald-100 text-emerald-700",
  purple:  "bg-purple-50  border-purple-100 text-purple-700",
  rose:    "bg-rose-50    border-rose-100   text-rose-700",
  indigo:  "bg-indigo-50  border-indigo-100 text-indigo-700",
  teal:    "bg-teal-50    border-teal-100   text-teal-700",
  slate:   "bg-slate-50   border-slate-200  text-slate-600",
};

// ── Animated counter ──────────────────────────────────────────────────────────
function Counter({ value }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (!value) return;
    const steps = 24;
    const step = value / steps;
    let cur = 0;
    const t = setInterval(() => {
      cur = Math.min(cur + step, value);
      setDisplay(Math.round(cur));
      if (cur >= value) clearInterval(t);
    }, 30);
    return () => clearInterval(t);
  }, [value]);
  return <>{display.toLocaleString()}</>;
}

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({ stat, value, loading }) {
  return (
    <div className={`border rounded-2xl p-5 flex flex-col gap-3 transition-all hover:shadow-md ${COLOR[stat.color]}`}>
      <div className="flex items-center justify-between">
        <span className="text-lg">{stat.icon}</span>
        {loading
          ? <div className="w-12 h-5 bg-current opacity-10 rounded animate-pulse" />
          : <span className="text-2xl font-black tabular-nums">
              {value !== undefined ? <Counter value={value} /> : "—"}
            </span>
        }
      </div>
      <div className="text-[10px] font-black uppercase tracking-widest opacity-70">{stat.label}</div>
    </div>
  );
}

// ── Feature Card ──────────────────────────────────────────────────────────────
function FeatureCard({ f }) {
  return (
    <a href={f.href} className="no-underline group">
      <div className={`border rounded-2xl p-5 transition-all hover:shadow-lg active:scale-95 cursor-pointer ${COLOR[f.color]}`}>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-2xl">{f.icon}</span>
          <span className="text-sm font-black text-slate-800 group-hover:underline">{f.label}</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {f.tables.map(t => (
            <span key={t} className="text-[9px] font-bold px-2 py-0.5 bg-white/70 rounded-full border border-current/20 font-mono">
              {t}
            </span>
          ))}
        </div>
      </div>
    </a>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function IntelligenceDashboard() {
  const [stats, setStats]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState("");
  const [lastFetch, setLastFetch] = useState(null);

  const fetchStats = async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/intelligence/stats`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStats(await res.json());
      setLastFetch(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStats(); }, []);

  return (
    <div className="max-w-6xl mx-auto px-6 py-12 space-y-10">
      {/* Hero */}
      <div className="bg-slate-900 text-white rounded-3xl p-10 sm:p-14 relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full -translate-y-1/2 translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-amber-500/5 rounded-full translate-y-1/2 -translate-x-1/2 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
          <div className="space-y-3">
            <div className="text-4xl">🧠</div>
            <h1 className="text-3xl sm:text-4xl font-black tracking-tight">DB Intelligence Layer</h1>
            <p className="text-slate-400 text-sm max-w-lg leading-relaxed">
              Live read-out of all 20 MySQL tables. Every feature routes exclusively through this layer — no JSON files, no hardcoded data.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-emerald-500/20">MySQL Only</span>
              <span className="px-3 py-1 bg-amber-500/20 text-amber-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-amber-500/20">20 Tables</span>
              <span className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-[10px] font-black uppercase tracking-widest border border-blue-500/20">Indexed Joins</span>
            </div>
          </div>
          <div className="shrink-0 text-right space-y-2">
            <button
              onClick={fetchStats}
              disabled={loading}
              className="h-11 px-6 bg-white/10 hover:bg-white/20 text-white border border-white/20 rounded-xl text-xs font-black uppercase tracking-widest transition-all disabled:opacity-40 flex items-center gap-2"
            >
              {loading
                ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Refreshing…</>
                : <>↻ Refresh</>}
            </button>
            {lastFetch && (
              <div className="text-[10px] text-slate-500">
                Last updated {lastFetch.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-rose-50 border border-rose-100 rounded-2xl p-5 flex gap-3 items-center">
          <span className="text-xl">⚠️</span>
          <div>
            <div className="text-xs font-black text-rose-800 uppercase tracking-widest mb-1">Intelligence Layer Unreachable</div>
            <div className="text-xs text-rose-600">{error} — ensure the backend is running and /intelligence/stats is registered.</div>
          </div>
        </div>
      )}

      {/* Platform Stats Grid */}
      <section>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-1 h-6 bg-slate-900 rounded-full" />
          <h2 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Live Table Counts</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {TABLE_STATS.map(stat => (
            <StatCard
              key={stat.key}
              stat={stat}
              value={stats?.[stat.key]}
              loading={loading}
            />
          ))}
        </div>
      </section>

      {/* Feature Routing Cards */}
      <section>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-1 h-6 bg-slate-900 rounded-full" />
          <h2 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Feature → Table Routing</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map(f => <FeatureCard key={f.id} f={f} />)}
        </div>
      </section>

      {/* API Endpoint Reference */}
      <section>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-1 h-6 bg-slate-900 rounded-full" />
          <h2 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Intelligence API Endpoints</h2>
        </div>
        <div className="bg-slate-900 rounded-2xl p-6 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/10">
                <th className="pb-3 pr-6 text-[10px] font-black text-slate-400 uppercase tracking-widest">Endpoint</th>
                <th className="pb-3 pr-6 text-[10px] font-black text-slate-400 uppercase tracking-widest">Feature</th>
                <th className="pb-3 text-[10px] font-black text-slate-400 uppercase tracking-widest">Tables</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {[
                ["/intelligence/bns/mapping",      "BNS Mapper",        "section_mapping + sections"],
                ["/intelligence/bns/search",        "BNS Search",        "section_mapping"],
                ["/intelligence/predict/facts/:cn", "Predict Outcome",   "case_facts + cases"],
                ["/intelligence/predict/result/:cn","AI Prediction",     "case_predictions"],
                ["/intelligence/adr/:cn",           "ADR Checker",       "adr_suitability"],
                ["/intelligence/lok-adalat-awards", "Settlement Data",   "lok_adalat_awards"],
                ["/intelligence/similar/:cn",       "Similar Cases",     "similar_cases + citations"],
                ["/intelligence/ecourts/:key",      "eCourts Cache",     "ecourts_case_status"],
                ["/intelligence/report/:cn",        "Legal Reports",     "case_section_reports + acts"],
                ["/intelligence/summary/:cn",       "Summaries",         "case_summaries"],
                ["/intelligence/translation/:cn",   "Translation",       "case_translations"],
                ["/intelligence/case/:cn",          "Full Intelligence", "7 tables (360° view)"],
                ["/intelligence/stats",             "Platform Stats",    "12 tables (this page)"],
              ].map(([ep, feat, tables]) => (
                <tr key={ep} className="hover:bg-white/5 transition-colors">
                  <td className="py-2.5 pr-6 font-mono text-cyan-400 text-[11px]">{ep}</td>
                  <td className="py-2.5 pr-6 text-slate-300 font-bold text-[11px]">{feat}</td>
                  <td className="py-2.5 text-slate-500 text-[11px]">{tables}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Rules Banner */}
      <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-6 flex gap-4">
        <span className="text-2xl mt-0.5">✅</span>
        <div className="space-y-1">
          <div className="text-xs font-black text-emerald-900 uppercase tracking-widest">Routing Rules Enforced</div>
          <div className="text-xs text-emerald-700 leading-relaxed">
            MySQL is the <strong>only</strong> source of truth · No static JSON · No hardcoded legal data ·
            sections_backup is never queried in production · All writes go through indexed upserts ·
            SELECT * is never used.
          </div>
        </div>
      </div>
    </div>
  );
}
