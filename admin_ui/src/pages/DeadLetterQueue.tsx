import { useCallback, useEffect, useState } from "react";
import { getDlqSummary, getDlqItems, retryDlqItems, purgeDlq } from "../api/endpoints";
import type { DlqItem } from "../api/endpoints";

const QUEUES = ["queue:delivery", "queue:deletion", "queue:credit"];

const queueLabels: Record<string, string> = {
  "queue:delivery": "Delivery",
  "queue:deletion": "Deletion",
  "queue:credit": "Credit",
};

export default function DeadLetterQueue() {
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [selectedQueue, setSelectedQueue] = useState(QUEUES[0]);
  const [items, setItems] = useState<DlqItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await getDlqSummary();
      setSummary(data);
    } catch {
      /* ignore */
    }
  }, []);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getDlqItems(selectedQueue);
      setItems(data.items);
      setTotal(data.total);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [selectedQueue]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleRetry = async (count: number) => {
    setActionStatus("Retrying...");
    try {
      const res = await retryDlqItems(selectedQueue, count);
      setActionStatus(`Retried ${res.retried} item(s)`);
      fetchSummary();
      fetchItems();
      setTimeout(() => setActionStatus(null), 3000);
    } catch {
      setActionStatus("Retry failed");
    }
  };

  const handlePurge = async () => {
    if (!confirm(`Permanently delete all failed jobs from ${queueLabels[selectedQueue]}?`)) return;
    setActionStatus("Purging...");
    try {
      const res = await purgeDlq(selectedQueue);
      setActionStatus(`Purged ${res.purged} item(s)`);
      fetchSummary();
      fetchItems();
      setTimeout(() => setActionStatus(null), 3000);
    } catch {
      setActionStatus("Purge failed");
    }
  };

  const totalFailed = Object.values(summary).reduce((a, b) => a + b, 0);

  return (
    <>
      <h1>Dead Letter Queue</h1>
      <p style={{ color: "#666", marginTop: -8 }}>
        Failed worker jobs land here for inspection and retry.
      </p>

      {actionStatus && (
        <div style={{ padding: "8px 16px", background: "#e8f5e9", borderRadius: 6, marginBottom: 12, fontWeight: 500 }}>
          {actionStatus}
        </div>
      )}

      {/* Summary cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        {QUEUES.map((q) => (
          <div
            key={q}
            onClick={() => setSelectedQueue(q)}
            style={{
              flex: 1,
              padding: "16px 20px",
              background: selectedQueue === q ? "#e3f2fd" : "#fff",
              border: selectedQueue === q ? "2px solid #1976d2" : "1px solid #ddd",
              borderRadius: 8,
              cursor: "pointer",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 28, fontWeight: 700, color: (summary[q] || 0) > 0 ? "#d32f2f" : "#388e3c" }}>
              {summary[q] || 0}
            </div>
            <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>{queueLabels[q]} DLQ</div>
          </div>
        ))}
        <div style={{
          flex: 1,
          padding: "16px 20px",
          background: "#fff3e0",
          border: "1px solid #ff9800",
          borderRadius: 8,
          textAlign: "center",
        }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: totalFailed > 0 ? "#e65100" : "#388e3c" }}>
            {totalFailed}
          </div>
          <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>Total Failed</div>
        </div>
      </div>

      {/* Actions bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
        <strong>{queueLabels[selectedQueue]} DLQ — {total} item(s)</strong>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => handleRetry(1)}
          disabled={total === 0}
          style={{ background: "#1976d2", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer" }}
        >
          Retry 1
        </button>
        <button
          onClick={() => handleRetry(total || 1)}
          disabled={total === 0}
          style={{ background: "#388e3c", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer" }}
        >
          Retry All ({total})
        </button>
        <button
          onClick={handlePurge}
          disabled={total === 0}
          style={{ background: "#d32f2f", color: "#fff", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer" }}
        >
          Purge All
        </button>
        <button
          onClick={() => { fetchSummary(); fetchItems(); }}
          style={{ padding: "6px 14px", cursor: "pointer" }}
        >
          Refresh
        </button>
      </div>

      {/* Items table */}
      {loading ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p style={{ color: "#888", textAlign: "center", padding: 32 }}>No failed jobs in this queue.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: 8 }}>#</th>
              <th style={{ textAlign: "left", padding: 8 }}>Error</th>
              <th style={{ textAlign: "left", padding: 8 }}>Job Data</th>
              <th style={{ textAlign: "left", padding: 8 }}>Failed At</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={idx} style={{ borderTop: "1px solid #eee" }}>
                <td style={{ padding: 8 }}>{idx + 1}</td>
                <td style={{ padding: 8, color: "#d32f2f", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.error || "—"}
                </td>
                <td style={{ padding: 8, maxWidth: 400 }}>
                  <pre style={{ margin: 0, fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                    {JSON.stringify(item.job, null, 2)}
                  </pre>
                </td>
                <td style={{ padding: 8, whiteSpace: "nowrap" }}>
                  {item.failed_at ? new Date(item.failed_at * 1000).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
