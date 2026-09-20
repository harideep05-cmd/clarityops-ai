import { useRef, useState } from "react";
import { api, downloadDocument } from "./api";
import Members from "./Members";
import "./App.css";

const suggestions = [
  "How many casual leave days do employees receive?",
  "When should I submit an expense claim?",
  "What should I do if my company laptop is lost?",
];

function App() {
  const [credential, setCredential] = useState("");
  const [token, setToken] = useState("");
  const [documents, setDocuments] = useState([]);
  const [status, setStatus] = useState(null);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const input = useRef(null);
  const activeToken = useRef("");
  const canManage = status?.permissions?.manage_documents === true;

  function reportError(error) {
    if (activeToken.current !== token) return;
    if (error.status === 401 || error.code === "access_revoked") {
      lock();
      setError("Your access expired or was revoked. Ask your workspace owner for new access.");
    } else setError(error.message);
  }

  async function connect(event) {
    event.preventDefault();
    setBusy("connect");
    setError("");
    try {
      const [info, list] = await Promise.all([
        api("/status", credential),
        api("/documents", credential),
      ]);
      setStatus(info);
      setDocuments(list.documents);
      activeToken.current = credential;
      setToken(credential);
      setCredential("");
      setQuestion("");
      setAsked("");
      setResult(null);
      setNotice("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  async function upload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setNotice("");
    if (!file.name.toLowerCase().endsWith(".pdf"))
      return setError("Choose a text-based PDF file.");
    if (file.size > 10 * 1024 * 1024)
      return setError("PDFs must be 10 MB or smaller.");
    setBusy("upload");
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await api("/upload", token, { method: "POST", body: form });
      if (activeToken.current !== token) return;
      const list = await api("/documents", token);
      if (activeToken.current !== token) return;
      setDocuments(list.documents);
      setNotice(
        data.duplicate
          ? "This document is already in your workspace."
          : `${data.document.filename} is ready for questions.`,
      );
    } catch (e) {
      reportError(e);
    } finally {
      if (activeToken.current === token) setBusy("");
    }
  }

  async function ask(event) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy("ask");
    setError("");
    setResult(null);
    setAsked(question.trim());
    setNotice("");
    try {
      const answer = await api("/ask", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: question.trim() }),
      });
      if (activeToken.current === token) setResult(answer);
    } catch (e) {
      reportError(e);
    } finally {
      if (activeToken.current === token) setBusy("");
    }
  }

  async function remove(doc) {
    if (
      !window.confirm(
        `Remove ${doc.filename}? Its original PDF and searchable content will be deleted from this workspace.`,
      )
    )
      return;
    setBusy("delete");
    setError("");
    setNotice("");
    try {
      await api(`/documents/${doc.id}`, token, { method: "DELETE" });
      if (activeToken.current !== token) return;
      setDocuments(documents.filter((d) => d.id !== doc.id));
      setResult(null);
      setAsked("");
      setNotice(`${doc.filename} was removed.`);
    } catch (e) {
      reportError(e);
    } finally {
      if (activeToken.current === token) setBusy("");
    }
  }

  function lock() {
    activeToken.current = "";
    setBusy("");
    setToken("");
    setDocuments([]);
    setStatus(null);
    setQuestion("");
    setAsked("");
    setResult(null);
    setError("");
    setNotice("");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="ClarityOps AI home">
          <span className="brand-mark">C</span>
          <span>
            ClarityOps <span className="brand-ai">AI</span>
          </span>
        </a>
        <div className="topbar-right">
          <span className="workspace-label">Company knowledge</span>
          {token && (
            <button className="quiet-button" disabled={!!busy} onClick={lock}>
              Lock workspace
            </button>
          )}
        </div>
      </header>
      {!token ? (
        <main className="unlock-layout">
          <div className="unlock-intro">
            <p className="eyebrow">YOUR COMPANY, IN CONTEXT</p>
            <h1>
              Clear answers.
              <br />
              From your documents.
            </h1>
            <p>
              Find the policies, procedures, and details your team needs, with
              evidence you can check.
            </p>
            <div className="intro-steps">
              <span>01 &nbsp; Add your PDFs</span>
              <span>02 &nbsp; Ask a question</span>
              <span>03 &nbsp; Check the source</span>
            </div>
          </div>
          <form className="unlock-card" onSubmit={connect}>
            <span className="small-mark">WORKSPACE ACCESS</span>
            <h2>Open your workspace</h2>
            <p>Enter the access token provided by your workspace owner.</p>
            <label htmlFor="access-token">Workspace access token</label>
            <input
              id="access-token"
              type="password"
              autoComplete="off"
              value={credential}
              onChange={(e) => setCredential(e.target.value)}
              required
              disabled={!!busy}
            />
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <button className="primary" disabled={!!busy || !credential.trim()}>
              {busy === "connect" ? "Connecting…" : "Open workspace →"}
            </button>
            <p className="fine-print">
              Access lasts until you lock or reload this page.
            </p>
          </form>
        </main>
      ) : (
        <main className="workspace">
          <div className="page-heading">
            <div>
              <p className="eyebrow">{status?.workspace?.name} · {status?.member?.role}</p>
              <h1>Company knowledge</h1>
              <p>
                Ask a question. Get an answer you can trace back to the source.
              </p>
            </div>
            <span className="count-badge">
              {documents.length} document{documents.length === 1 ? "" : "s"}{" "}
              ready
            </span>
          </div>
          <div aria-live="polite">
            {notice && (
              <div className="notice" role="status">
                {notice}
              </div>
            )}
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {status && !status.gemini_configured && (
            <div className="setup-notice">
              Documents can be indexed, but answer generation needs setup. The
              workspace owner must configure Gemini on the server.
            </div>
          )}
          {status && !status.embedding_files_present && (
            <div className="setup-notice">
              Document search needs setup. Ask the workspace owner to prepare
              the local search model.
            </div>
          )}
          <div className="workspace-grid">
            <aside className="documents-panel">
              <div className="panel-title">
                <h2>Documents</h2>
                <span>{documents.length.toString().padStart(2, "0")}</span>
              </div>
              <p className="panel-description">
                Build a trusted source for your team.
              </p>
              {canManage && <><input
                ref={input}
                type="file"
                accept=".pdf,application/pdf"
                onChange={upload}
                aria-label="Upload a PDF"
                className="file-input"
                disabled={!!busy}
              />
              <button
                className="upload-button"
                disabled={!!busy}
                onClick={() => input.current.click()}
              >
                <span aria-hidden="true">↑</span>
                {busy === "upload" ? "Processing document…" : "Upload PDF"}
              </button>
              <p className="fine-print upload-hint">
                Text-based PDF · Up to 10 MB · 100 pages
                <br />
                Scanned PDFs need a text layer.
              </p></>}
              <div className="document-list" aria-live="polite">
                {documents.length === 0 ? (
                  <div className="empty-docs">
                    <div className="paper-icon" aria-hidden="true">
                      ≡
                    </div>
                    <h3>Your knowledge starts here</h3>
                    <p>{canManage ? "Upload a handbook, policy, or SOP to begin." : "Your workspace owner can add company documents here."}</p>
                  </div>
                ) : (
                  documents.map((doc) => (
                    <article className="document" key={doc.id}>
                      <span className="pdf-label">PDF</span>
                      <div className="document-details">
                        <h3>{doc.filename}</h3>
                        <p>
                          {doc.page_count} page{doc.page_count === 1 ? "" : "s"}{" "}
                          <span aria-hidden="true">·</span> Ready
                        </p>
                      </div>
                      {canManage && <button
                        className="remove-button"
                        onClick={() => remove(doc)}
                        disabled={!!busy}
                        aria-label={`Remove ${doc.filename}`}
                        title="Remove document"
                      >
                        ×
                      </button>}
                      {doc.warnings.map((w) => (
                        <p key={w} className="document-warning">
                          {w}
                        </p>
                      ))}
                    </article>
                  ))
                )}
              </div>
              <p className="workspace-note">
                {status?.workspace_mode === "members"
                  ? "Documents are shared within your company. Owners manage knowledge; employees can ask questions and download sources."
                  : "Local demo: everyone with this shared token can read and remove documents."}
              </p>
            </aside>
            <section
              className="question-panel"
              aria-label="Ask your company documents"
            >
              <div className="question-header">
                <span className="small-mark">KNOWLEDGE ASSISTANT</span>
                <span className="evidence-label">
                  <span aria-hidden="true">●</span> Answers with sources
                </span>
              </div>
              <h2>What would you like to know?</h2>
              <form onSubmit={ask}>
                <label className="sr-only" htmlFor="question">
                  Company question
                </label>
                <textarea
                  id="question"
                  placeholder="For example, how many casual leave days do employees receive?"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  maxLength={1500}
                  disabled={!!busy}
                  rows={4}
                />
                <div className="question-actions">
                  <span>
                    {documents.length
                      ? "Grounded in your uploaded documents"
                      : canManage ? "Upload a document to start asking questions" : "Ask your workspace owner to add documents"}
                  </span>
                  <button
                    className="primary"
                    disabled={
                      !!busy || question.trim().length < 2 || !documents.length
                    }
                  >
                    {busy === "ask" ? "Finding an answer…" : "Ask question →"}
                  </button>
                </div>
              </form>
              {!result && !asked && (
                <div className="suggestions">
                  <p>Try asking</p>
                  {suggestions.map((s) => (
                    <button
                      disabled={!!busy}
                      key={s}
                      onClick={() => setQuestion(s)}
                    >
                      {s}
                      <span aria-hidden="true">↗</span>
                    </button>
                  ))}
                </div>
              )}
              {busy === "ask" && (
                <div className="answer-loading" role="status">
                  <span className="loading-dot" />
                  Searching your documents and checking the evidence…
                </div>
              )}
              {result && (
                <section
                  className="answer-section"
                  aria-live="polite"
                  aria-label="Answer"
                >
                  <div className="answer-heading">
                    <h3>
                      {result.status === "answered"
                        ? "Answer"
                        : "More information needed"}
                    </h3>
                    <span>
                      {result.sources.length
                        ? `${result.sources.length} source${result.sources.length === 1 ? "" : "s"}`
                        : "No supported answer"}
                    </span>
                  </div>
                  <p className="asked-question">{asked}</p>
                  <div className="answer-text">{result.answer}</div>
                  {!!result.sources.length && (
                    <div className="sources">
                      <h4>Check the evidence</h4>
                      {result.sources.map((source) => (
                        <details key={source.id} className="source" open>
                          <summary>
                            <span className="source-id">{source.id}</span>
                            <span>{source.document}</span>
                            <span className="page-label">
                              Page {source.page}
                            </span>
                          </summary>
                          {source.quotes.map((text, i) => (
                            <blockquote key={i}>{text}</blockquote>
                          ))}
                          <button
                            className="text-button"
                            disabled={!!busy}
                            onClick={async () => {
                              try {
                                await downloadDocument(source, token);
                              } catch (e) {
                                reportError(e);
                              }
                            }}
                          >
                            Download source PDF ↓
                          </button>
                        </details>
                      ))}
                    </div>
                  )}
                  {result.status !== "answered" && (
                    <p className="answer-hint">
                      Try a more specific question or upload a document that
                      covers this topic.
                    </p>
                  )}
                </section>
              )}
              <p className="privacy-note">
                Your question and selected document excerpts are sent to Gemini
                to generate answers. Check the cited source before acting on a
                policy.
              </p>
            </section>
          </div>
          {status?.permissions?.manage_members && <Members token={token} memberId={status.member.id} onAccessError={reportError} />}
        </main>
      )}
      <footer className="footer">
        <span>ClarityOps AI</span>
        <span>Company knowledge, made clear.</span>
      </footer>
    </div>
  );
}

export default App;
