import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearLog,
  getLogs,
  getLogSources,
  getActiveRateLimits,
  type LogResponse,
  type LogSource,
  type RateLimitEntry,
} from "../api/endpoints";

const LEVEL_COLORS: Record<string, string> = {
  ERROR: "#e74c3c",
  WARNING: "#f39c12",
  INFO: "#2ecc71",
  DEBUG: "#95a5a6",
};

function colorize(line: string): { color: string; level: string } {
  for (const [level, color] of Object.entries(LEVEL_COLORS)) {
    if (line.includes(`[${level}]`)) return { color, level };
  }
  return { color: "#ccc", level: "" };
}

export default function Logs() {
  const [sources, setSources] = useState<LogSource[]>([]);
  const [activeSource, setActiveSource] = useState("backend");
  const [logData, setLogData] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [tail, setTail] = useState(200);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [showRateLimits, setShowRateLimits] = useState(false);
  const [rateLimits, setRateLimits] = useState<RateLimitEntry[]>([]);
  const [rlLoading, setRlLoading] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSources = useCallback(async () => {
    try {
      const s = await getLogSources();
      setSources(s);
    } catch {
      // ignore
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getLogs(activeSource, tail, search, level);
      setLogData(data);
    } catch (e) {
      setLogData({
        source: activeSource,
        filename: "",
        total_lines: 0,
        lines: [`Failed to fetch logs: ${e instanceof Error ? e.message : "Unknown error"}`],
        file_size_bytes: 0,
      });
    }
    setLoading(false);
  }, [activeSource, tail, search, level]);

  const fetchRL = useCallback(async () => {
    setRlLoading(true);
    try {
      const data = await getActiveRateLimits();
      setRateLimits(data.entries);
    } catch {
      setRateLimits([]);
    }
    setRlLoading(false);
  }, []);

  // Initial load
  useEffect(() => {
    fetchSources();
    if (!showRateLimits) fetchLogs();
  }, [fetchSources, fetchLogs, showRateLimits]);

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        if (showRateLimits) fetchRL();
        else fetchLogs();
      }, 3000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, fetchLogs, showRateLimits]);

  // Auto-scroll to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logData]);

  const handleClear = async () => {
    if (!confirm(`Clear ${activeSource} logs?`)) return;
    await clearLog(activeSource);
    fetchLogs();
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>📜 Logs</h1>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={fetchLogs}
            disabled={loading}
            style={{
              padding: "8px 16px",
              background: "#3498db",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            {loading ? "⏳" : "🔄"} Refresh
          </button>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 14 }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto (3s)
          </label>
        </div>
      </div>

      {/* Source tabs + info */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {sources.map((s) => (
          <button
            key={s.name}
            onClick={() => { setActiveSource(s.name); setShowRateLimits(false); }}
            style={{
              padding: "8px 16px",
              background: !showRateLimits && activeSource === s.name ? "#2c3e50" : "#ecf0f1",
              color: !showRateLimits && activeSource === s.name ? "#fff" : "#333",
              border: "none",
              borderRadius: "4px 4px 0 0",
              cursor: "pointer",
              fontWeight: !showRateLimits && activeSource === s.name ? 600 : 400,
            }}
          >
            {s.name.toUpperCase()}
            <span style={{ fontSize: 11, marginLeft: 6, opacity: 0.7 }}>
              {s.exists ? s.size_human : "No file"}
            </span>
          </button>
        ))}
        <button
          onClick={() => { setShowRateLimits(true); fetchRL(); }}
          style={{
            padding: "8px 16px",
            background: showRateLimits ? "#2c3e50" : "#ecf0f1",
            color: showRateLimits ? "#fff" : "#333",
            border: "none",
            borderRadius: "4px 4px 0 0",
            cursor: "pointer",
            fontWeight: showRateLimits ? 600 : 400,
          }}
        >
          ⚡ RATE LIMITS
        </button>
      </div>

      {showRateLimits ? (
        /* ── Rate Limits Panel ── */
        <div>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
            {rlLoading ? "Loading..." : `${rateLimits.length} tracked key(s)`}
          </div>
          {rateLimits.length === 0 && !rlLoading && (
            <p style={{ color: "#999", fontStyle: "italic" }}>No active rate-limit counters in Redis.</p>
          )}
          {rateLimits.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f8f9fa", textAlign: "left" }}>
                  <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Key</th>
                  <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Count</th>
                  <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Limit</th>
                  <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Remaining</th>
                  <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>TTL</th>
                  <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {rateLimits.map((rl) => (
                  <tr key={rl.key} style={{ background: rl.exceeded ? "#ffeaea" : "transparent" }}>
                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee", fontFamily: "monospace" }}>{rl.key}</td>
                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>{rl.count}</td>
                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>{rl.limit}</td>
                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>{rl.remaining}</td>
                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>{rl.ttl_seconds}s</td>
                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee", fontWeight: 600, color: rl.exceeded ? "#e74c3c" : "#2ecc71" }}>
                      {rl.exceeded ? "EXCEEDED" : "OK"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <>
      {/* Filters */}
      <div
        style={{
          display: "flex",
          gap: 10,
          marginBottom: 12,
          padding: 10,
          background: "#f8f9fa",
          borderRadius: 4,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <label style={{ fontSize: 13 }}>
          Lines:
          <select
            value={tail}
            onChange={(e) => setTail(Number(e.target.value))}
            style={{ marginLeft: 4, padding: "4px 8px" }}
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
          </select>
        </label>

        <label style={{ fontSize: 13 }}>
          Level:
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            style={{ marginLeft: 4, padding: "4px 8px" }}
          >
            <option value="">All</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </label>

        <input
          type="text"
          placeholder="🔍 Search logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && fetchLogs()}
          style={{ flex: 1, minWidth: 150, padding: "6px 10px", border: "1px solid #ccc", borderRadius: 4 }}
        />

        <button
          onClick={handleClear}
          style={{
            padding: "6px 12px",
            background: "#e74c3c",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          🗑 Clear
        </button>
      </div>

      {/* Stats bar */}
      {logData && (
        <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
          Showing {logData.lines.length} of {logData.total_lines} total lines
          {logData.file_size_bytes > 0 && ` · File: ${(logData.file_size_bytes / 1024).toFixed(1)} KB`}
        </div>
      )}

      {/* Log output */}
      <div
        style={{
          background: "#1e1e1e",
          color: "#d4d4d4",
          fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
          fontSize: 12,
          lineHeight: 1.6,
          padding: 16,
          borderRadius: 8,
          maxHeight: "60vh",
          overflow: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {logData?.lines.length === 0 && (
          <div style={{ color: "#666", fontStyle: "italic" }}>No log entries found.</div>
        )}
        {logData?.lines.map((line, i) => {
          const { color } = colorize(line);
          return (
            <div key={i} style={{ color, borderBottom: "1px solid #2a2a2a", padding: "2px 0" }}>
              {line}
            </div>
          );
        })}
        <div ref={logEndRef} />
      </div>
        </>
      )}
    </>
  );
}
