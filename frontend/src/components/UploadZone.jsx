import { useState } from "react";

export default function UploadZone({ onUploaded, api }) {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile]         = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress]   = useState(0);
  const [error, setError]         = useState("");

  const handleFiles = (f) => {
    if (!f || !f.name.match(/\.(pdf|png|jpg|jpeg|tiff?)$/i)) {
      setError("Accepted formats: PDF, PNG, JPG, TIFF"); return;
    }
    setFile(f); setError("");
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    handleFiles(e.dataTransfer.files?.[0]);
  };

  const upload = async () => {
    if (!file || uploading) return;
    setUploading(true); setProgress(10); setError("");
    try {
      const tick = setInterval(() => setProgress(p => Math.min(p + 12, 85)), 400);
      const fd = new FormData();
      fd.append("file", file);
      const data = await api("/cases/upload-case", { method: "POST", body: fd });
      clearInterval(tick); setProgress(100);
      setTimeout(() => { setProgress(0); setUploading(false); }, 800);
      if (data.error) { setError(data.error); return; }
      onUploaded(data);
    } catch (e) { setError(e.message); setUploading(false); setProgress(0); }
  };

  return (
    <div className="glass-card p-8 mb-10">
      {/* Header */}
      <div className="flex items-center gap-3 mb-7">
        <span className="status-dot" />
        <h3 className="label-xs">Legal Document Intake</h3>
      </div>

      {/* Drop zone */}
      <div
        id="upload-drop-zone"
        className={`relative group rounded-2xl p-12 text-center transition-all duration-300 cursor-pointer overflow-hidden border-2 border-dashed ${
          dragOver
            ? "border-gold-400/60 bg-gold-400/05 scale-[0.99]"
            : file
              ? "border-emerald-500/40 bg-emerald-500/04"
              : "border-white/08 bg-white/02 hover:border-gold-400/30 hover:bg-gold-400/03"
        }`}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif"
          disabled={uploading}
          className="absolute inset-0 opacity-0 cursor-pointer z-10 w-full h-full"
          onChange={e => handleFiles(e.target.files?.[0])}
        />

        {/* Animated border glow on drag */}
        {dragOver && (
          <div className="absolute inset-0 rounded-2xl pointer-events-none"
            style={{boxShadow:"inset 0 0 40px rgba(201,168,76,0.08)"}} />
        )}

        <div className="space-y-5 relative z-0">
          <div className={`mx-auto w-20 h-20 rounded-full flex items-center justify-center text-3xl transition-all duration-300 border ${
            file
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 scale-110"
              : "border-gold-400/20 bg-gold-400/08 text-gold-400 group-hover:scale-110"
          }`}>
            {file ? "✓" : "📥"}
          </div>
          <div>
            <h4 className="legal-heading text-xl mb-2">
              {file ? "Document Ready" : "Drop Your Document"}
            </h4>
            <p className="text-sm text-slate-500 max-w-xs mx-auto leading-relaxed">
              {file
                ? <span className="text-emerald-400 font-mono text-xs">{file.name}</span>
                : "Drag & drop or click to browse — PDF, PNG, JPG, TIFF"
              }
            </p>
          </div>
          {!file && (
            <div className="flex items-center justify-center gap-6 pt-2">
              {["PDF","DOCX","PNG","TIFF"].map(fmt => (
                <span key={fmt} className="text-[10px] font-bold tracking-widest uppercase text-slate-600 border border-white/06 rounded px-2 py-1">
                  {fmt}
                </span>
              ))}
            </div>
          )}
        </div>

        {file && (
          <div className="mt-6 inline-flex items-center gap-3 px-4 py-2 rounded-full border border-gold-400/20 bg-gold-400/06 animate-fade-up">
            <span className="text-gold-400 font-bold text-[10px] uppercase tracking-widest">Selected</span>
            <span className="text-sm font-mono text-slate-300 max-w-[200px] truncate">{file.name}</span>
            <button
              className="w-5 h-5 rounded-full bg-white/06 hover:bg-rose-500/20 text-slate-500 hover:text-rose-400 transition-colors flex items-center justify-center text-[10px]"
              onClick={e => { e.stopPropagation(); setFile(null); setError(""); }}
            >✕</button>
          </div>
        )}
      </div>

      {/* Progress */}
      {progress > 0 && (
        <div className="mt-7 space-y-2">
          <div className="flex justify-between label-xs">
            <span>Intelligent Processing</span>
            <span className="text-gold-400">{progress}%</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{background:"rgba(255,255,255,0.05)"}}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width:`${progress}%`,
                background:"linear-gradient(90deg, #C9A84C, #e4b84a)",
                boxShadow:"0 0 12px rgba(201,168,76,0.5)",
              }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-5 p-4 rounded-xl border border-rose-500/20 bg-rose-500/08 flex items-center gap-3 animate-fade-up">
          <span className="text-rose-400 text-lg">⚠</span>
          <p className="text-rose-300 text-sm">{error}</p>
        </div>
      )}

      {/* Action */}
      <div className="mt-7 flex items-center gap-3">
        <button
          id="upload-btn"
          className="btn btn-primary flex-1 h-13 text-sm gap-3 disabled:opacity-40 disabled:grayscale rounded-xl"
          style={{height:"52px"}}
          onClick={upload}
          disabled={!file || uploading}
        >
          {uploading ? (
            <><div className="w-4 h-4 border-2 border-navy-900/40 border-t-navy-900 rounded-full animate-spin" />Analysing Case Data…</>
          ) : (
            <>⚖ Process Document</>
          )}
        </button>
        {file && !uploading && (
          <button
            className="btn btn-ghost h-13 px-5 rounded-xl"
            style={{height:"52px"}}
            onClick={() => { setFile(null); setError(""); }}
          >Clear</button>
        )}
      </div>
    </div>
  );
}
