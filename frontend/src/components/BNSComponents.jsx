import { useState, useEffect, useCallback, useRef } from "react";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

// ── Change type badge ─────────────────────────────────────────────────────────
const CHANGE_COLOR = {
  retained:  { bg: "bg-emerald-50", border: "border-emerald-100", text: "text-emerald-700", label: "Retained" },
  modified:  { bg: "bg-amber-50",  border: "border-amber-100",   text: "text-amber-700",   label: "Modified" },
  merged:    { bg: "bg-blue-50",   border: "border-blue-100",    text: "text-blue-700",    label: "Merged"   },
  replaced:  { bg: "bg-rose-50",   border: "border-rose-100",    text: "text-rose-700",    label: "Replaced" },
  split:     { bg: "bg-purple-50", border: "border-purple-100",  text: "text-purple-700",  label: "Split"    },
};

function ChangeBadge({ type }) {
  const c = CHANGE_COLOR[type] || { bg: "bg-slate-50", border: "border-slate-100", text: "text-slate-400", label: type || "—" };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${c.bg} ${c.border} ${c.text}`}>
      {c.label}
    </span>
  );
}

// ── Era badge ─────────────────────────────────────────────────────────────────
function EraBadge({ era }) {
  const map = {
    pre_2024:    { cls: "bg-rose-50 text-rose-600 border-rose-100",     label: "⚠ Pre-2024 Era" },
    post_2024:   { cls: "bg-emerald-50 text-emerald-600 border-emerald-100", label: "✓ BNS Compliant" },
    transitional:{ cls: "bg-amber-50 text-amber-600 border-amber-100",  label: "⚡ Transitional" },
  };
  const e = map[era] || { cls: "bg-slate-50 text-slate-400 border-slate-100", label: "Unknown Era" };
  return <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border ${e.cls}`}>{e.label}</span>;
}

// ── BNS Panel (for case-report view) ─────────────────────────────────────────
export function BNSPanel({ caseNumber }) {
  const [report, setReport]   = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!caseNumber) return;
    (async () => {
      try {
        const res = await fetch(`${API}/bns/case-report/${encodeURIComponent(caseNumber)}`);
        if (res.ok) setReport((await res.json()).report);
      } catch (_) {} finally { setLoading(false); }
    })();
  }, [caseNumber]);

  if (loading) return <BNSSkeleton />;
  if (!report) return null;

  const deprecated = (report.sections_found || []).filter(s => s.is_deprecated);

  return (
    <div className="bg-white border border-slate-200 rounded-3xl shadow-xl overflow-hidden animate-in slide-in-from-bottom-8 duration-700">
      <div className="bg-slate-900 px-8 py-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-white/10 rounded-xl flex items-center justify-center text-xl border border-white/10">📖</div>
          <div>
            <div className="text-sm font-black text-white uppercase tracking-[0.2em]">Legislative Audit</div>
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">IPC / CrPC / IEA → BNS / BNSS / BSA</div>
          </div>
        </div>
        {report && <EraBadge era={report.document_era} />}
      </div>

      <div className="p-8">
        {deprecated.length > 0 ? (
          <SectionTable sections={deprecated} title="Deprecated Citations Found" />
        ) : (
          <div className="py-12 text-center bg-emerald-50 rounded-3xl border border-emerald-100">
            <div className="text-4xl mb-4">✅</div>
            <h4 className="text-sm font-black text-emerald-800 uppercase tracking-widest">Modern Era Compliance Verified</h4>
            <p className="text-xs text-emerald-600/70 mt-2 font-medium">All citations follow post-July 1, 2024 standards.</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Reusable section table ────────────────────────────────────────────────────
function SectionTable({ sections, title }) {
  if (!sections?.length) return null;
  return (
    <div className="space-y-4">
      {title && <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{title}</div>}
      <div className="overflow-hidden border border-slate-100 rounded-2xl">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="px-5 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">Legacy Source</th>
              <th className="px-5 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">BNS Successor</th>
              <th className="px-5 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 text-right">Change</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {sections.map((s, i) => (
              <tr key={i} className="hover:bg-slate-50/50 transition-colors group">
                <td className="px-5 py-5">
                  <div className="font-mono text-sm font-black text-slate-700 group-hover:text-rose-600 transition-colors">
                    {s.act || s.cited_act} § {s.section || s.cited_section}
                  </div>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-tight mt-1 max-w-[200px] truncate">
                    {s.old_title || "Untitled Provision"}
                  </div>
                </td>
                <td className="px-5 py-5">
                  {s.new_section ? (
                    <div className="flex items-center gap-3">
                      <span className="text-slate-300 text-lg group-hover:translate-x-1 transition-transform">→</span>
                      <div>
                        <div className="font-mono text-sm font-black text-slate-800">
                          {s.new_act} § {s.new_section}
                        </div>
                        <div className="text-[10px] font-bold text-emerald-600 uppercase tracking-tight mt-1 max-w-[200px] truncate">
                          {s.new_title || "Modern Provision"}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs font-black text-slate-300 uppercase italic tracking-widest">Unmapped</span>
                  )}
                </td>
                <td className="px-5 py-5 text-right">
                  <ChangeBadge type={s.change_type} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Legal Section Content Formatter ──────────────────────────────────────────
// Transforms raw SQL legal text into structured, document-like clauses.
function LegalSectionFormatter({ actName, year, sectionNumber, sectionTitle, content, fullDescription, punishment, additionalInfo }) {
  // Use content or fullDescription as source text
  const rawText = content || fullDescription || "";

  // ── Parse raw text into structured blocks ──────────────────────────────────
  const parseContent = (text) => {
    if (!text.trim()) return [];

    // Split on main clause markers: (1), (2), … also handle "1.(1)" prefix artifacts
    // Strategy: find all positions of pattern markers, then slice between them
    const blocks = [];

    // Normalize "1.(1)" → "(1)" at start
    let normalized = text.replace(/^\d+\.\s*\((\d+)\)/, "($1)");

    // Split on top-level numbered clauses (1), (2), (3) …
    // Also detect Explanation, Illustration sections
    const CLAUSE_RE = /(?=\(\d+\)|\bExplanation\b|\bIllustration\b)/g;

    const parts = normalized.split(CLAUSE_RE).filter(s => s.trim());

    parts.forEach(part => {
      const trimmed = part.trim();
      if (!trimmed) return;

      if (/^Explanation\.?:?-?/i.test(trimmed)) {
        // Explanation block
        const body = trimmed.replace(/^Explanation\.?:?-?\s*/i, "").trim();
        blocks.push({ type: "explanation", text: body });
      } else if (/^Illustration\.?/i.test(trimmed)) {
        // Illustration block
        const body = trimmed.replace(/^Illustration\.?\s*/i, "").trim();
        blocks.push({ type: "illustration", text: body });
      } else if (/^\(\d+\)/.test(trimmed)) {
        // Main clause — check for embedded sub-clauses (a), (b), (c)
        const clauseMatch = trimmed.match(/^(\(\d+\))\s*([\s\S]*)/);
        if (clauseMatch) {
          const clauseNum = clauseMatch[1];
          const clauseBody = clauseMatch[2].trim();

          // Look for sub-clauses
          const SUB_RE = /(?=\([a-z]\))/g;
          const subParts = clauseBody.split(SUB_RE).filter(s => s.trim());

          if (subParts.length > 1 || /\([a-z]\)/.test(clauseBody)) {
            // Has sub-clauses
            const intro = subParts[0].replace(/\([a-z]\)[\s\S]*$/, "").trim();
            const subs = [];
            subParts.forEach(sp => {
              const sm = sp.trim().match(/^(\([a-z]\))\s*([\s\S]*)/);
              if (sm) {
                subs.push({ label: sm[1], text: sm[2].trim().replace(/;$/, ";") });
              }
            });
            blocks.push({ type: "clause_with_subs", num: clauseNum, intro, subs });
          } else {
            blocks.push({ type: "clause", num: clauseNum, text: clauseBody });
          }
        }
      } else {
        // Preamble / plain text before first clause
        blocks.push({ type: "preamble", text: trimmed });
      }
    });

    return blocks;
  };

  const blocks = parseContent(rawText);

  return (
    <div className="legal-doc font-serif" style={{ fontFamily: "'Georgia', 'Times New Roman', serif", lineHeight: 1.85 }}>
      {/* ── Act Heading ─────────────────────────────────────────────────── */}
      {actName && (
        <div className="text-center mb-6">
          <div className="text-base font-bold text-slate-800 tracking-wide">
            {actName}{year ? `, ${year}` : ""}
          </div>
          {sectionNumber && (
            <div className="text-sm text-slate-500 mt-1 font-medium">
              Section {sectionNumber}
            </div>
          )}
        </div>
      )}

      {/* ── Section Title ────────────────────────────────────────────────── */}
      {sectionTitle && (
        <div className="mb-5">
          <span className="font-bold text-slate-800 text-sm">
            {sectionNumber}. {sectionTitle}.{" "}
          </span>
          <span className="text-slate-500 font-normal">:</span>
        </div>
      )}

      {/* ── Parsed Clauses ───────────────────────────────────────────────── */}
      <div className="space-y-4 text-sm text-slate-700">
        {blocks.length > 0 ? (
          blocks.map((block, i) => {
            if (block.type === "preamble") {
              return (
                <p key={i} className="leading-relaxed">
                  {block.text}
                </p>
              );
            }
            if (block.type === "clause") {
              return (
                <div key={i} className="flex gap-3">
                  <span className="shrink-0 font-bold text-slate-600 w-8 text-right">{block.num}</span>
                  <p className="leading-relaxed flex-1">{block.text}</p>
                </div>
              );
            }
            if (block.type === "clause_with_subs") {
              return (
                <div key={i} className="space-y-2">
                  <div className="flex gap-3">
                    <span className="shrink-0 font-bold text-slate-600 w-8 text-right">{block.num}</span>
                    <p className="leading-relaxed flex-1">
                      {block.intro}
                      {block.intro && !block.intro.endsWith("—") && !block.intro.endsWith("–") ? "—" : ""}
                    </p>
                  </div>
                  <div className="ml-12 space-y-2 border-l-2 border-slate-100 pl-4">
                    {block.subs.map((sub, j) => (
                      <div key={j} className="flex gap-3">
                        <span className="shrink-0 font-medium text-slate-500 w-6 text-right">{sub.label}</span>
                        <p className="leading-relaxed flex-1">{sub.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            }
            if (block.type === "explanation") {
              return (
                <div key={i} className="mt-5 pt-4 border-t border-slate-100">
                  <div className="font-bold text-slate-700 mb-2 text-sm">Explanation.:-</div>
                  <p className="leading-relaxed text-slate-600 italic">{block.text}</p>
                </div>
              );
            }
            if (block.type === "illustration") {
              return (
                <div key={i} className="mt-5 pt-4 border-t border-slate-100">
                  <div className="font-bold text-slate-700 mb-2 text-sm">Illustration.</div>
                  <p className="leading-relaxed text-slate-600 whitespace-pre-line">{block.text}</p>
                </div>
              );
            }
            return null;
          })
        ) : (
          // Fallback: raw text if parsing produces nothing
          <p className="leading-relaxed whitespace-pre-wrap">{rawText}</p>
        )}
      </div>

      {/* ── Punishment ───────────────────────────────────────────────────── */}
      {punishment && (
        <div className="mt-6 pt-4 border-t border-rose-100">
          <div className="bg-rose-50 border border-rose-100 rounded-xl px-5 py-4">
            <div className="text-[9px] font-black text-rose-500 uppercase tracking-widest mb-2">Punishment</div>
            <p className="text-sm text-rose-800 leading-relaxed font-medium">{punishment}</p>
          </div>
        </div>
      )}

      {/* ── Additional Info ───────────────────────────────────────────────── */}
      {additionalInfo && (
        <div className="mt-6 pt-4 border-t border-slate-200 text-center">
          <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-full px-4 py-2 text-xs font-bold text-blue-700">
            <span>ℹ️</span>
            <span className="uppercase tracking-widest">Additional Info</span>
          </div>
          <p className="mt-2 text-xs text-slate-500 font-medium">{additionalInfo}</p>
        </div>
      )}
    </div>
  );
}

// ── Section Lookup (search by act + section number) ───────────────────────────
export function SectionLookupPage() {
  const [act, setAct]         = useState("IPC");
  const [section, setSection] = useState("");
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const handleLookup = async () => {
    if (!section.trim()) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}/bns/lookup?act=${act}&section=${encodeURIComponent(section.trim())}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Not found");
      setResult(json);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-10">
      {/* Search bar */}
      <div className="glass-card p-6 sm:p-8 overflow-hidden">
        <div className="flex items-center gap-3 mb-8 pb-5" style={{borderBottom:"1px solid var(--border-gold)"}}>
          <div className="w-2 h-2 rounded-full" style={{background:"#C9A84C",boxShadow:"0 0 8px rgba(201,168,76,0.5)"}} />
          <h3 className="label-xs">Section Discovery Engine</h3>
        </div>
        <div className="w-full flex flex-col sm:flex-row gap-3 mb-4">
          <select
            className="gold-select"
            style={{minWidth:"120px",width:"120px",flex:"0 0 auto"}}
            value={act} onChange={e => setAct(e.target.value)}
          >
            {["IPC","CrPC","IEA","BNS","BNSS","BSA"].map(a => <option key={a}>{a}</option>)}
          </select>
          <input
            className="gold-input"
            style={{flex:"1 1 0",minWidth:0}}
            value={section} onChange={e => setSection(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleLookup()}
            placeholder="Section e.g. 302, 438, 65B..."
          />
          <button
            className="btn btn-primary text-xs shrink-0"
            style={{height:"48px",padding:"0 1.5rem",whiteSpace:"nowrap"}}
            onClick={handleLookup} disabled={loading || !section.trim()}
          >
            {loading ? <span className="inline-block w-5 h-5 border-2 rounded-full animate-spin" style={{borderColor:"rgba(10,14,26,0.3)",borderTopColor:"#0A0E1A"}} /> : "Lookup"}
          </button>
        </div>
        {error && <div className="animate-fade-up p-3 rounded-xl text-xs font-bold flex items-center gap-2" style={{background:"rgba(248,81,73,0.10)",border:"1px solid rgba(248,81,73,0.30)",color:"#fca5a5"}}><span>⚠</span>{error}</div>}

        {result && (() => {
          // Support both old flat format and new nested format
          const oldAct     = result.old_section?.act     ?? result.old_act     ?? "";
          const oldSec     = result.old_section?.section ?? result.old_section ?? "";
          const oldTitle   = result.old_section?.title   ?? result.old_title   ?? "";
          const newAct     = result.mapped_section?.act     ?? result.new_act     ?? "";
          const newSec     = result.mapped_section?.section ?? result.new_section ?? "";
          const newTitle   = result.mapped_section?.title   ?? result.new_title   ?? "";
          const changeType = result.mapped_section?.change_type  ?? result.change_type  ?? "";
          const changeNotes= result.mapped_section?.change_notes ?? result.change_notes ?? "";
          const content    = result.details?.content          ?? "";
          const punishment = result.details?.punishment       ?? "";
          const fullDesc   = result.details?.full_description ?? "";
          const addInfo    = result.details?.additional_info  ?? "";

          return (
            <div className="animate-in zoom-in-95 duration-500 mt-8 space-y-4">
              {/* Main mapping card */}
              <div className="bg-slate-900 rounded-[2rem] p-8 sm:p-10 relative overflow-hidden border border-white/5">
                <div className="absolute top-0 right-0 p-10 opacity-5 pointer-events-none text-[12rem] font-black text-white">§</div>
                <div className="flex flex-col sm:flex-row items-center gap-10 mb-10">
                  <div className="text-center sm:text-left">
                    <div className="text-[10px] font-black text-slate-500 uppercase tracking-[0.3em] mb-2">Legacy Node</div>
                    <div className="text-4xl font-black text-white font-mono">{oldAct} § {oldSec}</div>
                    {oldTitle && <div className="text-xs font-bold text-slate-400 mt-2">{oldTitle}</div>}
                  </div>
                  <div className="w-14 h-14 rounded-full bg-white/5 flex items-center justify-center text-2xl text-amber-400 shadow-2xl border border-white/10 shrink-0">→</div>
                  <div className="text-center sm:text-left">
                    <div className="text-[10px] font-black text-amber-400 uppercase tracking-[0.3em] mb-2">Modern Node</div>
                    <div className="text-4xl font-black text-white font-mono">{newAct} § {newSec}</div>
                    {newTitle && <div className="text-xs font-bold text-amber-400 mt-2">{newTitle}</div>}
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-8 border-t border-white/10">
                  <div>
                    <div className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-2">Change Type</div>
                    <ChangeBadge type={changeType} />
                  </div>
                  {changeNotes && (
                    <div>
                      <div className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-2">Notes</div>
                      <p className="text-xs text-slate-300 leading-relaxed italic">"{changeNotes}"</p>
                    </div>
                  )}
                </div>
              </div>

              {/* ── Structured Legal Document Section Details ── */}
              {(content || punishment || fullDesc || addInfo) && (
                <div className="glass-card overflow-hidden">
                  <div className="px-6 py-4 flex items-center gap-2" style={{borderBottom:"1px solid var(--border-gold)"}}>
                    <span className="text-base">📋</span>
                    <span className="label-xs">Section Details — {newAct} {newSec}</span>
                  </div>
                  <div className="p-6 sm:p-8">
                    <LegalSectionFormatter
                      actName={newAct === "BNS" ? "Bharatiya Nyaya Sanhita" : newAct === "BNSS" ? "Bharatiya Nagarik Suraksha Sanhita" : newAct === "BSA" ? "Bharatiya Sakshya Adhiniyam" : newAct}
                      year={newAct === "BNS" || newAct === "BNSS" || newAct === "BSA" ? "2023" : ""}
                      sectionNumber={newSec}
                      sectionTitle={newTitle}
                      content={content}
                      fullDescription={fullDesc}
                      punishment={punishment}
                      additionalInfo={addInfo}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// ── FIR / Document Text Analyzer ─────────────────────────────────────────────
export function DraftAnalyzer() {
  const [text, setText]       = useState("");
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const analyze = async () => {
    if (!text.trim()) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}/bns/analyze-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, case_number: "DRAFT" }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Analysis failed");
      setResult(json);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-8">
      <div className="glass-card p-8">
        <div className="flex items-center gap-3 mb-6 pb-5" style={{borderBottom:"1px solid var(--border-gold)"}}>
          <div className="w-2 h-2 rounded-full" style={{background:"#C9A84C",boxShadow:"0 0 8px rgba(201,168,76,0.5)"}} />
          <h3 className="label-xs">FIR / Document Analyzer</h3>
        </div>
        <p className="body-text text-xs mb-6 leading-relaxed">
          Paste any FIR, charge sheet, petition, or judgment. The AI will extract every legal section citation and map it to BNS/BNSS/BSA.
        </p>
        <textarea
          className="gold-textarea"
          style={{height:"180px",resize:"vertical"}}
          placeholder={"Paste FIR text, charge sheet, or petition here...\n\nExample: 'The accused is charged under Section 302 IPC and Section 376 IPC...'"}
          value={text} onChange={e => setText(e.target.value)}
        />
        <div className="flex items-center justify-between mt-4">
          <span className="label-xs" style={{opacity:0.5}}>{text.length} characters</span>
          <button
            className="btn btn-secondary h-11 px-8"
            onClick={analyze} disabled={loading || !text.trim()}
          >
            {loading ? <><span className="inline-block w-4 h-4 border-2 rounded-full animate-spin" style={{borderColor:"rgba(201,168,76,0.3)",borderTopColor:"#C9A84C"}} /> Analyzing…</> : "⚡ Analyze Sections"}
          </button>
        </div>
        {error && <div className="mt-4 p-3 rounded-xl text-xs font-bold flex items-center gap-2" style={{background:"rgba(248,81,73,0.10)",border:"1px solid rgba(248,81,73,0.30)",color:"#fca5a5"}}><span>⚠</span>{error}</div>}
      </div>

      {result && (
        <div className="glass-card p-8 animate-fade-up">
          {/* Summary row */}
          <div className="flex flex-wrap gap-4 mb-8">
            <StatChip label="Sections Found" value={result.total_sections} color="slate" />
            <StatChip label="Deprecated" value={result.deprecated_count} color={result.deprecated_count > 0 ? "rose" : "emerald"} />
            <StatChip label="Unmapped" value={result.unmapped_count} color={result.unmapped_count > 0 ? "amber" : "emerald"} />
            <div className="flex items-center"><EraBadge era={result.document_era} /></div>
          </div>

          {result.deprecated_count > 0 && (
            <div className="bg-amber-50 border border-amber-100 rounded-2xl p-4 mb-6 flex gap-3">
              <span className="text-xl">⚖️</span>
              <div>
                <div className="text-xs font-black text-amber-900 uppercase tracking-tight mb-0.5">Modernization Required</div>
                <div className="text-xs text-amber-700 font-medium">{result.advice}</div>
              </div>
            </div>
          )}

          {result.sections_found?.length > 0 && (
            <SectionTable sections={result.sections_found} title={`All ${result.total_sections} Extracted Section(s)`} />
          )}
        </div>
      )}
    </div>
  );
}

// ── Draft Rewriter ────────────────────────────────────────────────────────────
export function DocumentRewriter() {
  const [draft, setDraft]     = useState("");
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [view, setView]       = useState("rewritten"); // original | rewritten

  const rewrite = async () => {
    if (!draft.trim()) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}/bns/rewrite-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft_text: draft }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Rewrite failed");
      setResult(json);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-8">
      <div className="glass-card p-8">
        <div className="flex items-center gap-3 mb-6 pb-5" style={{borderBottom:"1px solid var(--border-gold)"}}>
          <div className="w-2 h-2 rounded-full" style={{background:"rgba(168,126,210,0.9)",boxShadow:"0 0 8px rgba(168,126,210,0.4)"}} />
          <h3 className="label-xs">Petition / Draft Auto-Rewriter</h3>
        </div>
        <p className="body-text text-xs mb-6 leading-relaxed">
          Paste your draft petition, FIR, or legal notice. The AI will rewrite it with all deprecated IPC/CrPC/IEA sections replaced by BNS/BNSS/BSA equivalents.
        </p>
        <textarea
          className="gold-textarea"
          style={{height:"180px",resize:"vertical"}}
          placeholder="Paste draft petition or legal document here..."
          value={draft} onChange={e => setDraft(e.target.value)}
        />
        <div className="flex items-center justify-end mt-4">
          <button
            className="btn btn-secondary h-11 px-8"
            onClick={rewrite} disabled={loading || !draft.trim()}
          >
            {loading ? <><span className="inline-block w-4 h-4 border-2 rounded-full animate-spin" style={{borderColor:"rgba(201,168,76,0.3)",borderTopColor:"#C9A84C"}} /> Rewriting…</> : "✏️ Auto-Rewrite Draft"}
          </button>
        </div>
        {error && <div className="mt-4 p-3 rounded-xl text-xs font-bold flex items-center gap-2" style={{background:"rgba(248,81,73,0.10)",border:"1px solid rgba(248,81,73,0.30)",color:"#fca5a5"}}><span>⚠</span>{error}</div>}
      </div>

      {result && (
        <div className="glass-card p-8 animate-fade-up">
          {result.is_compliant ? (
            <div className="py-8 text-center bg-emerald-50 rounded-2xl border border-emerald-100">
              <div className="text-3xl mb-3">✅</div>
              <p className="text-sm font-black text-emerald-800">{result.message}</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-6">
                <div className="text-xs font-black text-slate-500 uppercase tracking-widest">{result.substitution_count} substitution(s) made</div>
                <div className="flex gap-2">
                  {["original","rewritten"].map(v => (
                    <button key={v} onClick={() => setView(v)}
                      className={`px-4 py-2 rounded-lg text-[11px] font-black uppercase tracking-widest transition-all ${view===v ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400 hover:bg-slate-200"}`}>
                      {v}
                    </button>
                  ))}
                </div>
              </div>

              {result.substitutions?.length > 0 && (
                <div className="mb-6 flex flex-wrap gap-2">
                  {result.substitutions.map((s, i) => (
                    <div key={i} className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 border border-amber-100 rounded-full text-xs font-bold">
                      <span className="text-rose-600 font-mono">{s.from}</span>
                      <span className="text-slate-400">→</span>
                      <span className="text-emerald-600 font-mono">{s.to}</span>
                      <ChangeBadge type={s.change_type} />
                    </div>
                  ))}
                </div>
              )}

              <div className="rounded-2xl p-6" style={{background:"rgba(5,8,15,0.6)",border:"1px solid var(--border-gold)"}}>
                <div className="label-xs mb-3">
                  {view === "original" ? "Original Text" : "Rewritten (BNS-Compliant) Text"}
                </div>
                <pre className="text-sm whitespace-pre-wrap leading-relaxed font-sans" style={{color:"var(--text-secondary)"}}>
                  {view === "original" ? result.original : result.rewritten}
                </pre>
              </div>

              <div className="flex justify-end mt-4">
                <button
                  className="px-5 py-2.5 text-xs font-black uppercase tracking-widest bg-emerald-600 text-white rounded-xl hover:bg-emerald-500 transition-colors"
                  onClick={() => navigator.clipboard.writeText(result.rewritten)}
                >📋 Copy Rewritten Draft</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Small stat chip ───────────────────────────────────────────────────────────
function StatChip({ label, value, color }) {
  const colors = {
    slate:   { bg:"rgba(255,255,255,0.05)",  border:"rgba(255,255,255,0.10)",  text:"var(--text-secondary)" },
    rose:    { bg:"rgba(248,81,73,0.10)",    border:"rgba(248,81,73,0.25)",    text:"#fca5a5" },
    emerald: { bg:"rgba(63,185,80,0.10)",    border:"rgba(63,185,80,0.25)",    text:"#86efac" },
    amber:   { bg:"rgba(227,179,65,0.10)",   border:"rgba(227,179,65,0.25)",   text:"#E3B341" },
  };
  const s = colors[color] || colors.slate;
  return (
    <div className="px-4 py-2 rounded-xl border text-xs font-black" style={{background:s.bg,borderColor:s.border,color:s.text}}>
      <span className="text-lg mr-1">{value}</span>{label}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
function BNSSkeleton() {
  return (
    <div className="glass-card p-8 animate-pulse">
      <div className="h-4 rounded w-1/4 mb-10" style={{background:"rgba(255,255,255,0.06)"}} />
      <div className="space-y-4">
        {[0,1,2].map(i => <div key={i} className="h-16 rounded-2xl w-full" style={{background:"rgba(255,255,255,0.04)"}} />)}
      </div>
    </div>
  );
}

// ── Aliases for compatibility ─────────────────────────────────────────────────
export { BNSPanel as BNSWarningBanner };
export { SectionLookupPage as SectionLookup };
export { DraftAnalyzer as DraftChecker };
