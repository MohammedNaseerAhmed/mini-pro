import { useState, useRef } from "react";

export default function UploadZone({ onUploaded, api }) {
    const [dragOver, setDragOver] = useState(false);
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState("");
    const inputRef = useRef(null);

    const handleFiles = (f) => {
        if (!f || !f.name.match(/\.(pdf|png|jpg|jpeg|tiff?)$/i)) {
            setError("Please upload a PDF or image file.");
            return;
        }
        setFile(f);
        setError("");
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files?.[0]);
    };

    const upload = async () => {
        if (!file || uploading) return;
        setUploading(true);
        setProgress(10);
        setError("");
        try {
            const tick = setInterval(() => setProgress((p) => Math.min(p + 12, 85)), 400);
            const fd = new FormData();
            fd.append("file", file);
            const data = await api("/cases/upload-case", { method: "POST", body: fd });
            clearInterval(tick);
            setProgress(100);
            setTimeout(() => { setProgress(0); setUploading(false); }, 800);
            if (data.error) { setError(data.error); return; }
            onUploaded(data);
        } catch (e) {
            setError(e.message);
            setUploading(false);
            setProgress(0);
        }
    };

    return (
        <div className="card">
            <div className="card-title"><span className="dot" />Upload Legal Document</div>
            <div
                id="upload-drop-zone"
                className={`upload-zone${dragOver ? " drag-over" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => !uploading && inputRef.current?.click()}
            >
                <input
                    ref={inputRef}
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif"
                    onChange={(e) => handleFiles(e.target.files?.[0])}
                />
                <span className="upload-icon">📄</span>
                <h3>{file ? "File Ready" : "Drop or Click to Upload"}</h3>
                <p>Supports PDF (digital or scanned), PNG, JPG — court petitions, FIRs, notices, judgments</p>
                {file && <div className="file-name">📎 {file.name}</div>}
            </div>

            {progress > 0 && (
                <div className="progress-bar-wrap" style={{ marginTop: 16 }}>
                    <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
                </div>
            )}
            {error && <p style={{ color: "var(--red)", fontSize: 13, marginTop: 10 }}>⚠ {error}</p>}
            <div className="action-row" style={{ marginTop: 16 }}>
                <button id="upload-btn" className="btn btn-primary" onClick={upload} disabled={!file || uploading}>
                    {uploading ? <><span className="spinner" /> Uploading…</> : "⬆ Upload & Analyze"}
                </button>
                {file && !uploading && (
                    <button className="btn btn-ghost" onClick={() => { setFile(null); setError(""); }}>
                        ✕ Clear
                    </button>
                )}
            </div>
        </div>
    );
}
