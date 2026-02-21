import { useState, useRef, useEffect } from "react";

function statusClass(s) {
    const m = (s || "").toLowerCase();
    if (m.includes("clean") || m.includes("complete")) return "cleaned";
    if (m.includes("pending")) return "pending";
    if (m.includes("fail")) return "failed";
    if (m.includes("process")) return "processing";
    return "complete";
}

function fmtDate(d) {
    if (!d) return "—";
    const dt = new Date(d);
    return dt.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export default function RecentCasesPanel({ api }) {
    const [cases, setCases] = useState([]);
    const [loading, setLoading] = useState(false);
    const [open, setOpen] = useState(true);

    const load = async () => {
        setLoading(true);
        try {
            const data = await api("/dashboard/cases?limit=15");
            setCases(Array.isArray(data?.cases) ? data.cases : []);
        } catch (_e) {
            setCases([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []); // eslint-disable-line

    return (
        <div className="card" style={{ animationDelay: "0.2s" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: open ? 16 : 0 }}>
                <div className="card-title" style={{ marginBottom: 0 }}>
                    <span className="dot" style={{ background: "var(--cyan)" }} />Recent Cases
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <button
                        className="btn btn-ghost"
                        style={{ padding: "6px 12px", fontSize: 12 }}
                        onClick={load}
                        disabled={loading}
                    >
                        {loading ? <span className="spinner" /> : "↻"} Refresh
                    </button>
                    <button className="collapse-btn" onClick={() => setOpen((o) => !o)}>
                        {open ? "▲ Hide" : "▼ Show"}
                    </button>
                </div>
            </div>

            {open && (
                <>
                    {cases.length === 0 && !loading && (
                        <div className="empty-state">
                            <span className="es-icon">📂</span>No cases uploaded yet.
                        </div>
                    )}
                    {cases.length > 0 && (
                        <table className="cases-table">
                            <thead>
                                <tr>
                                    <th>Case Number</th>
                                    <th>Title</th>
                                    <th>Status</th>
                                    <th>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {cases.map((c, i) => (
                                    <tr key={i}>
                                        <td style={{ fontFamily: "monospace", fontSize: 12, color: "var(--gold)" }}>
                                            {c.case_number}
                                        </td>
                                        <td style={{ color: "var(--text-muted)", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                            {c.title || "—"}
                                        </td>
                                        <td>
                                            <span className={`status-pill ${statusClass(c.processing_status)}`}>
                                                {c.processing_status || "unknown"}
                                            </span>
                                        </td>
                                        <td style={{ color: "var(--text-muted)", fontSize: 12 }}>
                                            {fmtDate(c.created_at)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </>
            )}
        </div>
    );
}
