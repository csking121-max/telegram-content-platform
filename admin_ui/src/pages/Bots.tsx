import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import {
  getBots, createBot, deleteBot, updateBot,
  announceBot, clearBotMessages, sendBotWelcome,
  bulkAnnounce, bulkClearMessages, bulkSendWelcome, bulkDeleteBots,
} from "../api/endpoints";

export default function Bots() {
  const { data: bots, loading, error, refetch } = useFetch(
    useCallback(() => getBots(), []),
  );
  const [form, setForm] = useState({ bot_username: "", bot_token: "", webhook_secret: "" });
  const [announceModal, setAnnounceModal] = useState<{ botId: number; botName: string } | null>(null);
  const [bulkAnnounceModal, setBulkAnnounceModal] = useState(false);
  const [announceText, setAnnounceText] = useState("");
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const allIds = (bots ?? []).map((b: any) => b.id);
  const allSelected = allIds.length > 0 && allIds.every((id: number) => selectedIds.has(id));

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(allIds));
  };

  const clearSelection = () => setSelectedIds(new Set());

  const showStatus = (msg: string, duration = 4000) => {
    setActionStatus(msg);
    setTimeout(() => setActionStatus(null), duration);
  };

  const handleAdd = async () => {
    if (!form.bot_username || !form.bot_token) return;
    await createBot(form);
    setForm({ bot_username: "", bot_token: "", webhook_secret: "" });
    refetch();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this bot?")) return;
    await deleteBot(id);
    refetch();
  };

  const handleCleanupChange = async (id: number, hours: number) => {
    await updateBot(id, { cleanup_hours: hours });
    refetch();
  };

  // Single-bot actions
  const handleAnnounce = async () => {
    if (!announceModal || !announceText.trim()) return;
    showStatus("Sending announcement...");
    try {
      const res = await announceBot(announceModal.botId, announceText.trim());
      showStatus(`Sent: ${res.sent}, Failed: ${res.failed}`);
      setAnnounceText("");
      setTimeout(() => setAnnounceModal(null), 2000);
    } catch {
      showStatus("Announcement failed");
    }
  };

  const handleClear = async (id: number, name: string) => {
    if (!confirm(`Clear all tracked messages for @${name}?`)) return;
    showStatus("Clearing messages...");
    try {
      const res = await clearBotMessages(id);
      showStatus(`Deleted: ${res.deleted}, Failed: ${res.failed}`);
    } catch {
      showStatus("Clear failed");
    }
  };

  const handleWelcome = async (id: number, name: string) => {
    if (!confirm(`Send welcome message to all users of @${name}?`)) return;
    showStatus("Sending welcome messages...");
    try {
      const res = await sendBotWelcome(id);
      showStatus(`Sent: ${res.sent}, Failed: ${res.failed}`);
    } catch {
      showStatus("Welcome send failed");
    }
  };

  // Bulk actions
  const ids = Array.from(selectedIds);

  const handleBulkAnnounce = async () => {
    if (!announceText.trim() || ids.length === 0) return;
    showStatus(`Sending announcement to ${ids.length} bot(s)...`);
    try {
      const res = await bulkAnnounce(ids, announceText.trim());
      const totals = res.results.reduce((a: any, r: any) => ({ sent: a.sent + (r.sent || 0), failed: a.failed + (r.failed || 0) }), { sent: 0, failed: 0 });
      showStatus(`Bulk announce: Sent ${totals.sent}, Failed ${totals.failed}`);
      setAnnounceText("");
      setBulkAnnounceModal(false);
      clearSelection();
    } catch {
      showStatus("Bulk announcement failed");
    }
  };

  const handleBulkClear = async () => {
    if (!confirm(`Clear messages for ${ids.length} selected bot(s)?`)) return;
    showStatus(`Clearing messages for ${ids.length} bot(s)...`);
    try {
      const res = await bulkClearMessages(ids);
      const totals = res.results.reduce((a: any, r: any) => ({ deleted: a.deleted + (r.deleted || 0), failed: a.failed + (r.failed || 0) }), { deleted: 0, failed: 0 });
      showStatus(`Bulk clear: Deleted ${totals.deleted}, Failed ${totals.failed}`);
      clearSelection();
    } catch {
      showStatus("Bulk clear failed");
    }
  };

  const handleBulkWelcome = async () => {
    if (!confirm(`Send welcome message via ${ids.length} selected bot(s)?`)) return;
    showStatus(`Sending welcome via ${ids.length} bot(s)...`);
    try {
      const res = await bulkSendWelcome(ids);
      const totals = res.results.reduce((a: any, r: any) => ({ sent: a.sent + (r.sent || 0), failed: a.failed + (r.failed || 0) }), { sent: 0, failed: 0 });
      showStatus(`Bulk welcome: Sent ${totals.sent}, Failed ${totals.failed}`);
      clearSelection();
    } catch {
      showStatus("Bulk welcome failed");
    }
  };

  const handleBulkDelete = async () => {
    if (!confirm(`DELETE ${ids.length} selected bot(s)? This cannot be undone.`)) return;
    showStatus(`Deleting ${ids.length} bot(s)...`);
    try {
      await bulkDeleteBots(ids);
      showStatus(`Deleted ${ids.length} bot(s)`);
      clearSelection();
      refetch();
    } catch {
      showStatus("Bulk delete failed");
    }
  };

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  const selCount = selectedIds.size;

  return (
    <>
      <h1>Bots</h1>

      {actionStatus && (
        <div style={{ padding: "8px 16px", background: "#e8f5e9", borderRadius: 6, marginBottom: 12, fontWeight: 500 }}>
          {actionStatus}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="bot username" value={form.bot_username} onChange={(e) => setForm({ ...form, bot_username: e.target.value })} />
        <input placeholder="bot token" value={form.bot_token} onChange={(e) => setForm({ ...form, bot_token: e.target.value })} />
        <input placeholder="webhook secret" value={form.webhook_secret} onChange={(e) => setForm({ ...form, webhook_secret: e.target.value })} />
        <button onClick={handleAdd}>Add Bot</button>
      </div>

      {/* Bulk Action Toolbar */}
      {selCount > 0 && (
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
          background: "#e3f2fd", borderRadius: 8, marginBottom: 12, flexWrap: "wrap",
          border: "1px solid #90caf9",
        }}>
          <span style={{ fontWeight: 600, marginRight: 4 }}>
            {selCount} bot{selCount > 1 ? "s" : ""} selected
          </span>
          <button
            onClick={() => { setBulkAnnounceModal(true); setAnnounceText(""); }}
            style={{ background: "#1976d2", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer", fontWeight: 500 }}
          >📢 Announce</button>
          <button
            onClick={handleBulkClear}
            style={{ background: "#f57c00", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer", fontWeight: 500 }}
          >🧹 Clear Messages</button>
          <button
            onClick={handleBulkWelcome}
            style={{ background: "#388e3c", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer", fontWeight: 500 }}
          >👋 Send Welcome</button>
          <button
            onClick={handleBulkDelete}
            style={{ background: "#d32f2f", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer", fontWeight: 500 }}
          >🗑️ Delete</button>
          <button
            onClick={clearSelection}
            style={{ background: "transparent", border: "1px solid #999", borderRadius: 4, padding: "6px 14px", cursor: "pointer" }}
          >✕ Deselect</button>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr>
            <th style={{ width: 36 }}>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                title="Select all"
                style={{ cursor: "pointer", width: 16, height: 16 }}
              />
            </th>
            <th>ID</th><th>Username</th><th>Status</th><th>Traffic</th>
            <th>Cleanup (hrs)</th><th>Created</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {bots?.map((b: any) => {
            const isSelected = selectedIds.has(b.id);
            return (
              <tr key={b.id} style={{ background: isSelected ? "#e3f2fd" : undefined }}>
                <td style={{ textAlign: "center" }}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(b.id)}
                    style={{ cursor: "pointer", width: 16, height: 16 }}
                  />
                </td>
                <td>{b.id}</td>
                <td>@{b.bot_username}</td>
                <td>{b.status === "active" ? "✅" : "❌"}</td>
                <td style={{ textAlign: "center", fontWeight: 600 }}>{b.user_count ?? 0}</td>
                <td style={{ textAlign: "center" }}>
                  <select
                    value={b.cleanup_hours ?? 0}
                    onChange={(e) => handleCleanupChange(b.id, Number(e.target.value))}
                    style={{ padding: "2px 4px" }}
                  >
                    <option value={0}>Off</option>
                    <option value={1}>1h</option>
                    <option value={2}>2h</option>
                    <option value={6}>6h</option>
                    <option value={12}>12h</option>
                    <option value={24}>24h</option>
                    <option value={48}>48h</option>
                  </select>
                </td>
                <td>{new Date(b.created_at).toLocaleDateString()}</td>
                <td style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  <button
                    title="Announce"
                    onClick={() => { setAnnounceModal({ botId: b.id, botName: b.bot_username }); setAnnounceText(""); }}
                    style={{ background: "#1976d2", color: "#fff", border: "none", borderRadius: 4, padding: "4px 8px", cursor: "pointer" }}
                  >📢</button>
                  <button
                    title="Clear Messages"
                    onClick={() => handleClear(b.id, b.bot_username)}
                    style={{ background: "#f57c00", color: "#fff", border: "none", borderRadius: 4, padding: "4px 8px", cursor: "pointer" }}
                  >🧹</button>
                  <button
                    title="Send Welcome"
                    onClick={() => handleWelcome(b.id, b.bot_username)}
                    style={{ background: "#388e3c", color: "#fff", border: "none", borderRadius: 4, padding: "4px 8px", cursor: "pointer" }}
                  >👋</button>
                  <button
                    title="Delete Bot"
                    onClick={() => handleDelete(b.id)}
                    style={{ background: "#d32f2f", color: "#fff", border: "none", borderRadius: 4, padding: "4px 8px", cursor: "pointer" }}
                  >🗑️</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Single Bot Announce Modal */}
      {announceModal && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999,
        }}>
          <div style={{ background: "#fff", padding: 24, borderRadius: 8, width: 480, maxWidth: "90vw" }}>
            <h3 style={{ marginTop: 0 }}>📢 Announce to @{announceModal.botName} users</h3>
            <textarea
              value={announceText}
              onChange={(e) => setAnnounceText(e.target.value)}
              placeholder="Type announcement message (Markdown supported)..."
              rows={5}
              style={{ width: "100%", fontSize: 14, padding: 8, borderRadius: 4, border: "1px solid #ccc" }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
              <button onClick={() => { setAnnounceModal(null); setActionStatus(null); }}>Cancel</button>
              <button
                onClick={handleAnnounce}
                disabled={!announceText.trim()}
                style={{ background: "#1976d2", color: "#fff", border: "none", borderRadius: 4, padding: "8px 20px", cursor: "pointer" }}
              >Send</button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Announce Modal */}
      {bulkAnnounceModal && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999,
        }}>
          <div style={{ background: "#fff", padding: 24, borderRadius: 8, width: 480, maxWidth: "90vw" }}>
            <h3 style={{ marginTop: 0 }}>📢 Announce to {selCount} bot{selCount > 1 ? "s" : ""}</h3>
            <p style={{ color: "#666", fontSize: 13, marginTop: -8 }}>
              Message will be sent to all users of the selected bots.
            </p>
            <textarea
              value={announceText}
              onChange={(e) => setAnnounceText(e.target.value)}
              placeholder="Type announcement message (Markdown supported)..."
              rows={5}
              style={{ width: "100%", fontSize: 14, padding: 8, borderRadius: 4, border: "1px solid #ccc" }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
              <button onClick={() => { setBulkAnnounceModal(false); setActionStatus(null); }}>Cancel</button>
              <button
                onClick={handleBulkAnnounce}
                disabled={!announceText.trim()}
                style={{ background: "#1976d2", color: "#fff", border: "none", borderRadius: 4, padding: "8px 20px", cursor: "pointer" }}
              >Send to All</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}