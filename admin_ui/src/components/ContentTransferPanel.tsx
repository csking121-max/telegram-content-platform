import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  cancelTransferJob,
  deleteTransferChannel,
  getActiveBots,
  getTransferChannels,
  getTransferJobs,
  getTransferPacks,
  saveTransferChannel,
  startTransferJob,
  type TransferChannel,
  type TransferJob,
  type TransferPackRow,
} from "../api/endpoints";
import type { Bot } from "../types";

const card: CSSProperties = {
  background: "#fff",
  border: "1px solid #ddd",
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
};
const input: CSSProperties = { width: "100%", padding: 8, border: "1px solid #ccc", borderRadius: 4 };
const btn = (bg: string): CSSProperties => ({
  padding: "8px 14px",
  background: bg,
  color: "#fff",
  border: "none",
  borderRadius: 5,
  cursor: "pointer",
  fontWeight: 600,
});
const th: CSSProperties = { textAlign: "left", padding: 8, borderBottom: "1px solid #ddd", fontSize: 12 };
const td: CSSProperties = { padding: 8, borderBottom: "1px solid #eee", fontSize: 12 };

export default function ContentTransferPanel() {
  const [channels, setChannels] = useState<TransferChannel[]>([]);
  const [packs, setPacks] = useState<TransferPackRow[]>([]);
  const [jobs, setJobs] = useState<TransferJob[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [selectedPackIds, setSelectedPackIds] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);

  const [form, setForm] = useState<TransferChannel>({
    name: "",
    channel_id: "",
    channel_link: "",
    bot_id: null,
  });
  const [includeAll, setIncludeAll] = useState(true);
  const [makeActiveAfter, setMakeActiveAfter] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [rate, setRate] = useState(2);

  const load = async () => {
    const [ch, pk, jb, bt] = await Promise.all([
      getTransferChannels(),
      getTransferPacks(),
      getTransferJobs(),
      getActiveBots(),
    ]);
    setChannels(ch);
    setPacks(pk);
    setJobs(jb);
    setBots(bt);
    if (!form.bot_id && bt[0]) setForm((prev) => ({ ...prev, bot_id: bt[0].id }));
  };

  useEffect(() => {
    load().catch(() => setMessage("Failed to load transfer data."));
    const timer = setInterval(() => getTransferJobs().then(setJobs).catch(() => undefined), 3000);
    return () => clearInterval(timer);
  }, []);

  const visiblePacks = useMemo(() => {
    return packs.filter((pack) => {
      const created = pack.created_at ? pack.created_at.slice(0, 10) : "";
      if (dateFrom && created < dateFrom) return false;
      if (dateTo && created > dateTo) return false;
      return true;
    });
  }, [packs, dateFrom, dateTo]);

  const selectChannel = (id: string) => {
    setSelectedChannelId(id);
    const channel = channels.find((c) => c.id === id);
    if (channel) setForm(channel);
  };

  const saveChannel = async () => {
    setSaving(true);
    setMessage("");
    try {
      const saved = await saveTransferChannel(form);
      const updated = await getTransferChannels();
      setChannels(updated);
      setSelectedChannelId(saved.id || "");
      setForm(saved);
      setMessage("Transfer channel saved.");
    } catch {
      setMessage("Failed to save transfer channel.");
    } finally {
      setSaving(false);
    }
  };

  const removeChannel = async () => {
    if (!selectedChannelId || !window.confirm("Delete this transfer channel?")) return;
    await deleteTransferChannel(selectedChannelId);
    setSelectedChannelId("");
    setForm({ name: "", channel_id: "", channel_link: "", bot_id: bots[0]?.id ?? null });
    setChannels(await getTransferChannels());
  };

  const togglePack = (id: number) => {
    setSelectedPackIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const startTransfer = async () => {
    if (!form.channel_id || !form.bot_id) {
      setMessage("Channel ID and delivery bot are required.");
      return;
    }
    if (!includeAll && selectedPackIds.size === 0 && !dateFrom && !dateTo) {
      setMessage("Select packs or use a date filter.");
      return;
    }

    setStarting(true);
    setMessage("");
    try {
      await startTransferJob({
        channel_id: form.channel_id,
        channel_name: form.name,
        channel_link: form.channel_link || "",
        bot_id: form.bot_id,
        pack_ids: Array.from(selectedPackIds),
        date_from: dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : null,
        date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : null,
        include_all: includeAll,
        make_active_after: makeActiveAfter,
        rate_per_minute: rate,
      });
      setJobs(await getTransferJobs());
      setMessage("Transfer job started.");
    } catch (err) {
      const detail = err && typeof err === "object" && "response" in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : "";
      setMessage(detail || "Failed to start transfer job.");
    } finally {
      setStarting(false);
    }
  };

  const cancelJob = async (id: string) => {
    await cancelTransferJob(id);
    setJobs(await getTransferJobs());
  };

  return (
    <div>
      {message && <div style={{ padding: 10, marginBottom: 12, background: "#eef7ff", borderRadius: 4 }}>{message}</div>}

      <div style={card}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Content Transfer</h2>
        <div style={{ display: "grid", gridTemplateColumns: "220px 1fr 1fr", gap: 12, alignItems: "end" }}>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>Saved Channel</label>
            <select value={selectedChannelId} onChange={(e) => selectChannel(e.target.value)} style={input}>
              <option value="">New channel</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.id}>{channel.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={input} />
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>Channel ID</label>
            <input value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })} style={{ ...input, fontFamily: "monospace" }} />
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>Channel Link</label>
            <input value={form.channel_link || ""} onChange={(e) => setForm({ ...form, channel_link: e.target.value })} style={input} />
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>Delivery Bot</label>
            <select value={form.bot_id || ""} onChange={(e) => setForm({ ...form, bot_id: Number(e.target.value) })} style={input}>
              {bots.map((bot) => <option key={bot.id} value={bot.id}>@{bot.bot_username}</option>)}
            </select>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button onClick={saveChannel} disabled={saving} style={btn(saving ? "#95a5a6" : "#27ae60")}>
            {saving ? "Saving..." : "Save Channel"}
          </button>
          {selectedChannelId && <button onClick={removeChannel} style={btn("#c0392b")}>Delete Channel</button>}
        </div>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Transfer Options</h3>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <label><input type="checkbox" checked={includeAll} onChange={(e) => setIncludeAll(e.target.checked)} /> All matching packs</label>
          <label><input type="checkbox" checked={makeActiveAfter} onChange={(e) => setMakeActiveAfter(e.target.checked)} /> Make selected channel active after transfer</label>
          <label>Rate/min <input type="number" min={0} value={rate} onChange={(e) => setRate(Number(e.target.value || 0))} style={{ width: 70, padding: 6 }} /></label>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>From Date</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={input} />
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>To Date</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={input} />
          </div>
          <button onClick={startTransfer} disabled={starting} style={btn(starting ? "#95a5a6" : "#2980b9")}>
            {starting ? "Starting..." : "Start Transfer"}
          </button>
        </div>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Content Packs ({visiblePacks.length})</h3>
        <div style={{ maxHeight: 280, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}></th>
                <th style={th}>ID</th>
                <th style={th}>Title</th>
                <th style={th}>Category</th>
                <th style={th}>Files</th>
                <th style={th}>Created</th>
              </tr>
            </thead>
            <tbody>
              {visiblePacks.map((pack) => (
                <tr key={pack.id}>
                  <td style={td}>
                    <input type="checkbox" checked={selectedPackIds.has(pack.id)} onChange={() => togglePack(pack.id)} disabled={includeAll} />
                  </td>
                  <td style={td}>{pack.id}</td>
                  <td style={td}>{pack.title}</td>
                  <td style={td}>{pack.access_type}</td>
                  <td style={td}>{pack.item_count}</td>
                  <td style={td}>{pack.created_at ? new Date(pack.created_at).toLocaleString() : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Transfer Jobs</h3>
        {jobs.length === 0 ? <p style={{ color: "#666" }}>No transfer jobs yet.</p> : jobs.map((job) => {
          const done = job.completed + job.failed;
          const pct = Math.round((done / Math.max(job.total, 1)) * 100);
          return (
            <div key={job.id} style={{ border: "1px solid #eee", borderRadius: 6, padding: 10, marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <strong>{job.id} - {job.status}</strong>
                {(job.status === "queued" || job.status === "processing") && (
                  <button onClick={() => cancelJob(job.id)} style={{ ...btn("#c0392b"), padding: "4px 10px" }}>Cancel</button>
                )}
              </div>
              <div style={{ height: 18, background: "#eee", borderRadius: 9, marginTop: 8, overflow: "hidden" }}>
                <div style={{ width: `${pct}%`, height: "100%", background: job.failed ? "#e67e22" : "#27ae60" }} />
              </div>
              <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                {done}/{job.total} processed, {job.failed} failed
                {job.error ? ` - ${job.error}` : ""}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
