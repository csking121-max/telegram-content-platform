import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import { getBackups, triggerBackup, downloadBackup } from "../api/endpoints";

interface BackupInfo {
  filename: string;
  size_bytes: number;
  size_human: string;
  created: string;
}

interface BackupListResponse {
  backups: BackupInfo[];
  total: number;
  last_status: { file: string; size: string; timestamp: string; status: string } | null;
}

export default function Backups() {
  const { data, loading, error, refetch } = useFetch<BackupListResponse>(
    useCallback(() => getBackups(), []),
  );

  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerResult(null);
    try {
      const res = await triggerBackup();
      setTriggerResult(res.success ? "✅ " + res.message : "❌ " + res.message);
      refetch();
    } catch (err: unknown) {
      setTriggerResult("❌ " + (err instanceof Error ? err.message : "Failed to trigger backup"));
    } finally {
      setTriggering(false);
    }
  };

  const handleDownload = async (filename: string) => {
    setDownloading(filename);
    try {
      const blob = await downloadBackup(filename);
      const url = window.URL.createObjectURL(new Blob([blob]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      alert("Failed to download backup");
    } finally {
      setDownloading(null);
    }
  };

  const scheduleInfo = [
    { time: "01:00 UTC", label: "Job 1" },
    { time: "06:00 UTC", label: "Job 2" },
    { time: "11:00 UTC", label: "Job 3" },
    { time: "16:00 UTC", label: "Job 4" },
    { time: "21:00 UTC", label: "Job 5" },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>💾 Database Backups</h1>
        <button
          onClick={handleTrigger}
          disabled={triggering}
          style={{
            padding: "10px 24px",
            background: triggering ? "#6c757d" : "#28a745",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: triggering ? "not-allowed" : "pointer",
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          {triggering ? "⏳ Running Backup..." : "🚀 Manual Backup + Push"}
        </button>
      </div>

      {triggerResult && (
        <div
          style={{
            padding: "12px 16px",
            marginBottom: 16,
            borderRadius: 6,
            background: triggerResult.startsWith("✅") ? "#d4edda" : "#f8d7da",
            color: triggerResult.startsWith("✅") ? "#155724" : "#721c24",
          }}
        >
          {triggerResult}
        </div>
      )}

      {/* Schedule Info */}
      <div style={{ background: "#fff", borderRadius: 8, padding: 20, marginBottom: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
        <h3 style={{ margin: "0 0 12px" }}>📅 Auto-Backup Schedule (5x daily)</h3>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {scheduleInfo.map((s) => (
            <div
              key={s.label}
              style={{
                padding: "8px 16px",
                background: "#e8f4fd",
                borderRadius: 6,
                border: "1px solid #b8daff",
                fontSize: 13,
              }}
            >
              <strong>{s.label}</strong>: {s.time}
            </div>
          ))}
        </div>
      </div>

      {/* Last Backup Status */}
      {data?.last_status && (
        <div style={{ background: "#fff", borderRadius: 8, padding: 20, marginBottom: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3 style={{ margin: "0 0 8px" }}>🔄 Last Backup</h3>
          <p style={{ margin: 0, color: "#555" }}>
            <strong>{data.last_status.file}</strong> — {data.last_status.size} —{" "}
            {new Date(data.last_status.timestamp).toLocaleString()} —{" "}
            <span style={{ color: data.last_status.status === "success" ? "#28a745" : "#dc3545", fontWeight: 600 }}>
              {data.last_status.status.toUpperCase()}
            </span>
          </p>
        </div>
      )}

      {/* Backup List */}
      <div style={{ background: "#fff", borderRadius: 8, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
        <h3 style={{ margin: "0 0 16px" }}>📦 Backup Files ({data?.total ?? 0})</h3>

        {loading && <p>Loading...</p>}
        {error && <p style={{ color: "red" }}>Error: {error}</p>}

        {data && data.backups.length === 0 && <p style={{ color: "#888" }}>No backups found.</p>}

        {data && data.backups.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #dee2e6", textAlign: "left" }}>
                <th style={{ padding: "8px 12px" }}>Filename</th>
                <th style={{ padding: "8px 12px" }}>Size</th>
                <th style={{ padding: "8px 12px" }}>Date</th>
                <th style={{ padding: "8px 12px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.backups.map((b) => (
                <tr key={b.filename} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 13 }}>{b.filename}</td>
                  <td style={{ padding: "8px 12px" }}>{b.size_human}</td>
                  <td style={{ padding: "8px 12px" }}>{new Date(b.created).toLocaleString()}</td>
                  <td style={{ padding: "8px 12px" }}>
                    <button
                      onClick={() => handleDownload(b.filename)}
                      disabled={downloading === b.filename}
                      style={{
                        padding: "4px 12px",
                        background: downloading === b.filename ? "#6c757d" : "#007bff",
                        color: "#fff",
                        border: "none",
                        borderRadius: 4,
                        cursor: downloading === b.filename ? "not-allowed" : "pointer",
                        fontSize: 12,
                      }}
                    >
                      {downloading === b.filename ? "⏳" : "⬇️ Download"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
