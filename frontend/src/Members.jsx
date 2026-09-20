import { useState } from "react";
import { api } from "./api";

export default function Members({ token, memberId, onAccessError }) {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState("employee");
  const [issued, setIssued] = useState(null);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function failed(error) {
    if (error.status === 401 || error.code === "access_revoked") onAccessError(error);
    else setError(error.message);
  }

  async function show() {
    if (open) {
      setIssued(null);
      setRevealed(false);
      setOpen(false);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await api("/members", token);
      setMembers(data.members);
      setOpen(true);
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }

  async function issue(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    setIssued(null);
    setRevealed(false);
    try {
      const result = await api("/members", token, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), role, expires_in_days: 30 }),
      });
      setMembers([...members, result.member]);
      setIssued(result);
      setName("");
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }

  async function revoke(member) {
    if (!window.confirm(`Revoke ${member.name}'s access? They will need a new token to return.`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(`/members/${member.id}`, token, { method: "DELETE" });
      setMembers(members.map((m) => m.id === member.id ? { ...m, revoked_at: new Date().toISOString() } : m));
      if (issued?.member.id === member.id) setIssued(null);
      setMessage(`Access revoked for ${member.name}.`);
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }

  return <section className="members-panel" aria-label="Workspace members">
    <button className="text-button" onClick={show} disabled={busy} aria-expanded={open}>
      {open ? "Close member access" : "Manage member access"}
    </button>
    {error && <p className="error" role="alert">{error}</p>}
    {open && <>
      <h2>Member access</h2>
      <p>Give each person their own access token. Employees can ask questions and download sources; owners can also manage documents and members.</p>
      <form className="member-form" onSubmit={issue}>
        <label>Member name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required disabled={busy} /></label>
        <label>Access role<select value={role} onChange={(e) => setRole(e.target.value)} disabled={busy}>
          <option value="employee">Employee</option><option value="owner">Owner</option>
        </select></label>
        <button className="primary" disabled={busy || !name.trim()}>Create 30-day access</button>
      </form>
      {issued && <div className="issued-access">
        <p>Access created for <strong>{issued.member.name}</strong>. Save this token now and share it privately. Closing this panel hides it permanently.</p>
        <label>New member token<input type={revealed ? "text" : "password"} value={issued.access_token} readOnly autoComplete="off" /></label>
        <div className="member-actions">
          <button className="text-button" onClick={() => setRevealed(!revealed)}>{revealed ? "Hide token" : "Reveal token"}</button>
          <button className="text-button" onClick={async () => {
            try { await navigator.clipboard.writeText(issued.access_token); setMessage("Token copied. Share it privately."); }
            catch { setError("Could not copy. Reveal the token and copy it privately."); }
          }}>Copy token</button>
        </div>
        <p className="fine-print">Expires {new Date(issued.member.expires_at).toLocaleDateString()}. ClarityOps cannot show this token again.</p>
      </div>}
      {message && <p className="notice" role="status">{message}</p>}
      <ul className="member-list">{members.map((m) => <li key={m.id}>
        <div><strong>{m.name}</strong><span>{m.role} · {m.revoked_at ? "Revoked" : `Expires ${new Date(m.expires_at).toLocaleDateString()}`}</span></div>
        {m.id === memberId ? <span>You</span> : !m.revoked_at && <button className="text-button" disabled={busy} onClick={() => revoke(m)} aria-label={`Revoke ${m.name}`}>Revoke access</button>}
      </li>)}</ul>
    </>}
  </section>;
}
