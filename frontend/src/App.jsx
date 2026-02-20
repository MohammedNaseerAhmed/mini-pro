import { useState } from "react";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

async function api(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options || {});
  return response.json();
}

export default function App() {
  const [file, setFile] = useState(null);
  const [caseNumber, setCaseNumber] = useState("");
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState("hi");
  const [uploadResult, setUploadResult] = useState(null);
  const [overview, setOverview] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [features, setFeatures] = useState(null);
  const [summary, setSummary] = useState(null);
  const [translation, setTranslation] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [similar, setSimilar] = useState(null);
  const [chat, setChat] = useState(null);
  const [cases, setCases] = useState([]);

  const uploadCase = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    const data = await api("/cases/upload-case", { method: "POST", body: formData });
    setUploadResult(data);
    if (data?.case_number) setCaseNumber(data.case_number);
  };

  const refreshDashboard = async () => {
    setOverview(await api("/dashboard/overview"));
    setMetrics(await api("/dashboard/metrics"));
    setCases((await api("/dashboard/cases?limit=15"))?.cases || []);
  };

  const checkFeatures = async () => {
    if (!caseNumber) return;
    setFeatures(await api(`/cases/features/${encodeURIComponent(caseNumber)}`));
  };

  const getSummary = async () => {
    if (!caseNumber) return;
    setSummary(await api(`/ai/summarize/${encodeURIComponent(caseNumber)}`));
  };

  const getTranslation = async () => {
    if (!caseNumber) return;
    setTranslation(await api(`/ai/translate/${encodeURIComponent(caseNumber)}?language=${encodeURIComponent(language)}`));
  };

  const getPrediction = async () => {
    if (!caseNumber) return;
    setPrediction(await api(`/prediction/${encodeURIComponent(caseNumber)}`));
  };

  const getSimilar = async () => {
    if (!caseNumber) return;
    setSimilar(await api(`/search/${encodeURIComponent(caseNumber)}`));
  };

  const askChat = async () => {
    if (!question) return;
    setChat(await api(`/chatbot/ask?q=${encodeURIComponent(question)}`));
  };

  return (
    <div className="page">
      <header>
        <h1>Legal AI Dashboard</h1>
        <p>Upload-only pipeline: OCR -> summary -> translation -> RAG -> similar-case -> prediction.</p>
      </header>

      <section className="card">
        <h2>Upload Case File</h2>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button onClick={uploadCase}>Upload</button>
        {uploadResult && <pre>{JSON.stringify(uploadResult, null, 2)}</pre>}
      </section>

      <section className="card grid2">
        <div>
          <h2>Case Control</h2>
          <input placeholder="CASE-..." value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} />
          <button onClick={checkFeatures}>Check Features</button>
          <button onClick={getSummary}>Summary (6-10 bullets)</button>
          <div style={{ display: "flex", gap: "8px", marginTop: 8 }}>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="hi">Hindi</option>
              <option value="te">Telugu</option>
              <option value="ur">Urdu</option>
              <option value="simple_en">Simple English</option>
            </select>
            <button onClick={getTranslation}>Translate</button>
          </div>
          <button onClick={getSimilar}>Similar Cases</button>
          <button onClick={getPrediction}>Prediction</button>
        </div>
        <div>
          <h2>Dashboard</h2>
          <button onClick={refreshDashboard}>Refresh</button>
          {overview && <pre>{JSON.stringify(overview, null, 2)}</pre>}
          {metrics && <pre>{JSON.stringify(metrics, null, 2)}</pre>}
        </div>
      </section>

      <section className="card">
        <h2>Legal Chatbot (RAG)</h2>
        <textarea
          rows={4}
          placeholder="Ask legal question, ask summary, or ask translation."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button onClick={askChat}>Ask</button>
        {chat && <pre>{JSON.stringify(chat, null, 2)}</pre>}
      </section>

      <section className="card grid2">
        <div>{features && <pre>{JSON.stringify(features, null, 2)}</pre>}</div>
        <div>{summary && <pre>{JSON.stringify(summary, null, 2)}</pre>}</div>
      </section>
      <section className="card grid2">
        <div>{translation && <pre>{JSON.stringify(translation, null, 2)}</pre>}</div>
        <div>{prediction && <pre>{JSON.stringify(prediction, null, 2)}</pre>}</div>
      </section>
      <section className="card">{similar && <pre>{JSON.stringify(similar, null, 2)}</pre>}</section>

      <section className="card">
        <h2>Recent Cases</h2>
        <table>
          <thead>
            <tr>
              <th>Case Number</th>
              <th>Title</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((row, idx) => (
              <tr key={row.case_number || idx}>
                <td>{row.case_number}</td>
                <td>{row.title}</td>
                <td>{row.processing_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
