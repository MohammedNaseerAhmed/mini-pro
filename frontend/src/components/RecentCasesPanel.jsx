import { useState, useEffect } from "react";

const STATUS_CFG = {
  completed:  { label:"Completed",  dot:"bg-emerald-400", text:"text-emerald-400", ring:"border-emerald-400/25 bg-emerald-400/08" },
  cleaned:    { label:"Cleaning",   dot:"bg-amber-400",   text:"text-amber-400",   ring:"border-amber-400/25 bg-amber-400/08"   },
  extracted:  { label:"Extracted",  dot:"bg-blue-400",    text:"text-blue-400",    ring:"border-blue-400/25 bg-blue-400/08"     },
  predicted:  { label:"Predicted",  dot:"bg-purple-400",  text:"text-purple-400",  ring:"border-purple-400/25 bg-purple-400/08" },
  processing: { label:"Processing", dot:"bg-gold-400",    text:"text-gold-400",    ring:"border-gold-400/25 bg-gold-400/08"     },
  pending:    { label:"Pending",    dot:"bg-slate-500",   text:"text-slate-500",   ring:"border-slate-500/25 bg-slate-500/08"   },
  failed:     { label:"Failed",     dot:"bg-rose-400",    text:"text-rose-400",    ring:"border-rose-400/25 bg-rose-400/08"     },
};

function statusChip(s) {
  const key = (s||"").toLowerCase().replace(/\s+/g,"");
  let cfg = STATUS_CFG.pending;
  if (key.includes("complet"))  cfg = STATUS_CFG.completed;
  else if (key.includes("clean"))   cfg = STATUS_CFG.cleaned;
  else if (key.includes("predict")) cfg = STATUS_CFG.predicted;
  else if (key.includes("process")) cfg = STATUS_CFG.processing;
  else if (key.includes("extract")) cfg = STATUS_CFG.extracted;
  else if (key.includes("fail"))    cfg = STATUS_CFG.failed;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest border ${cfg.ring} ${cfg.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function fmtDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-IN", { day:"2-digit", month:"short" });
}

export default function RecentCasesPanel({ api }) {
  const [cases, setCases]     = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen]       = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api("/dashboard/cases?limit=15");
      setCases(Array.isArray(data?.cases) ? data.cases : []);
    } catch { setCases([]); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  return (
    <div className="glass-card overflow-hidden p-0">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/06"
        style={{background:"rgba(5,8,15,0.4)"}}>
        <div className="flex items-center gap-3">
          <div className="w-1.5 h-1.5 rounded-full bg-gold-400" style={{boxShadow:"0 0 8px rgba(201,168,76,0.6)"}} />
          <h3 className="label-xs">Case Repository</h3>
          {cases.length > 0 && (
            <span className="text-[9px] font-black px-2 py-0.5 rounded-full border border-gold-400/20 bg-gold-400/08 text-gold-400">
              {cases.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            className="label-xs text-slate-600 hover:text-gold-400 flex items-center gap-1.5 transition-colors disabled:opacity-30"
            onClick={load} disabled={loading}
          >
            {loading
              ? <div className="w-3 h-3 border-2 border-slate-600 border-t-gold-400 rounded-full animate-spin" />
              : <span>↻</span>}
            Refresh
          </button>
          <div className="w-px h-3 bg-white/08" />
          <button
            className="label-xs text-slate-600 hover:text-slate-300 transition-colors"
            onClick={() => setOpen(o => !o)}
          >{open ? "Hide" : "Show"}</button>
        </div>
      </div>

      {open && (
        <div className="overflow-x-auto">
          {/* Empty state */}
          {cases.length === 0 && !loading && (
            <div className="py-20 flex flex-col items-center justify-center opacity-30">
              <div className="text-4xl mb-4">📂</div>
              <p className="text-sm font-medium text-slate-500 italic" style={{fontFamily:"'Cormorant Garamond',serif",fontSize:"16px"}}>
                Repository is empty — upload your first document above
              </p>
            </div>
          )}

          {loading && cases.length === 0 && (
            <div className="p-8 space-y-3">
              {[...Array(4)].map((_,i) => (
                <div key={i} className="flex gap-4 items-center animate-fade-up" style={{animationDelay:`${i*60}ms`}}>
                  <div className="shimmer h-4 w-32 rounded" />
                  <div className="shimmer h-4 flex-1 rounded" />
                  <div className="shimmer h-4 w-20 rounded" />
                  <div className="shimmer h-4 w-16 rounded" />
                </div>
              ))}
            </div>
          )}

          {cases.length > 0 && (
            <table className="w-full text-left border-collapse">
              <thead>
                <tr style={{background:"rgba(5,8,15,0.3)"}}>
                  {["Reference","Matter","Jurisdiction","Workflow","Date"].map((h,i) => (
                    <th key={h} className={`px-6 py-3 label-xs border-b border-white/05 ${i===2?"hidden lg:table-cell":""} ${i===4?"text-right":""}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/04">
                {cases.map((c, i) => (
                  <tr key={i}
                    className="hover:bg-gold-400/03 transition-colors group animate-fade-up"
                    style={{animationDelay:`${i*30}ms`}}>
                    <td className="px-6 py-4 align-middle">
                      <span className="font-mono text-[11px] font-bold text-gold-300/80 bg-gold-400/06 border border-gold-400/15 px-2 py-1 rounded group-hover:border-gold-400/30 transition-colors">
                        {c.case_number}
                      </span>
                    </td>
                    <td className="px-6 py-4 align-middle">
                      <div className="max-w-xs xl:max-w-md truncate text-sm text-slate-400 group-hover:text-slate-200 transition-colors">
                        {c.title || <span className="italic text-slate-600">Untitled</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4 align-middle hidden lg:table-cell">
                      <div className="text-xs text-slate-600 truncate max-w-[180px]">
                        {c.court_name || "—"}
                      </div>
                    </td>
                    <td className="px-6 py-4 align-middle">
                      {statusChip(c.processing_status)}
                    </td>
                    <td className="px-6 py-4 align-middle text-right">
                      <span className="font-mono text-[10px] text-slate-600 tabular-nums">{fmtDate(c.created_at)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
