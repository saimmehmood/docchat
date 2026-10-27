import { useRef, useState } from "react";

async function apiError(res) {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

export default function App() {
  const fileInput = useRef(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploading, setUploading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setUploadStatus(`Uploading ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/upload", { method: "POST", body: form });
      if (!res.ok) throw new Error(await apiError(res));
      const data = await res.json();
      setUploadStatus(`Indexed ${data.filename}: ${data.pages} pages, ${data.chunks} chunks.`);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
      fileInput.current.value = "";
    }
  }

  async function handleAsk(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setQuestion("");
    setAsking(true);
    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (!res.ok) throw new Error(await apiError(res));
      const data = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: data.answer, sources: data.sources }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "error", text: err.message }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <main>
      <h1>DocChat</h1>

      <section className="upload">
        <button onClick={() => fileInput.current.click()} disabled={uploading}>
          {uploading ? "Uploading…" : "Upload PDF"}
        </button>
        <input ref={fileInput} type="file" accept="application/pdf" hidden onChange={handleUpload} />
        {uploadStatus && <span className="status">{uploadStatus}</span>}
      </section>

      <section className="chat">
        {messages.length === 0 && <p className="empty">Upload a PDF, then ask a question about it.</p>}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <p>{m.text}</p>
            {m.sources?.length > 0 && (
              <details>
                <summary>Sources</summary>
                <ol>
                  {m.sources.map((s) => (
                    <li key={s.id} title={s.snippet}>
                      {s.source}, page {s.page}
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        ))}
        {asking && <div className="msg assistant pending">Thinking…</div>}
      </section>

      <form className="ask" onSubmit={handleAsk}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your documents…"
          disabled={asking}
        />
        <button type="submit" disabled={asking || !question.trim()}>
          Send
        </button>
      </form>
    </main>
  );
}
