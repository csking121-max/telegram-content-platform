import { useEffect, useMemo, useState } from "react";
import {
  bulkUpdateSettings,
  clearExpiredCooldowns,
  extendCooldown,
  getActiveCooldowns,
  getPlatformSettings,
  removeCooldown,
  type CooldownRecord,
} from "../api/endpoints";

const LIMIT_KEY = "cooldown_links_limit";
const SECONDS_KEY = "cooldown_seconds";

function formatSeconds(total: number) {
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

export default function Cooldowns() {
  const [limit, setLimit] = useState("5");
  const [cooldownSeconds, setCooldownSeconds] = useState("3600");
  const [cooldowns, setCooldowns] = useState<CooldownRecord[]>([]);
  const [extendSeconds, setExtendSeconds] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const currentRule = useMemo(() => {
    const n = Number(limit || 0);
    const sec = Number(cooldownSeconds || 0);
    return `Users are blocked on the ${n + 1}th allowed deep-link access within 24 hours for ${formatSeconds(sec)}.`;
  }, [limit, cooldownSeconds]);

  async function loadAll() {
    setLoading(true);
    try {
      const [settings, active] = await Promise.all([
        getPlatformSettings("cooldown"),
        getActiveCooldowns(),
      ]);
      const limitSetting = settings.find((s) => s.key === LIMIT_KEY);
      const secondsSetting = settings.find((s) => s.key === SECONDS_KEY);
      setLimit(limitSetting?.value || "5");
      setCooldownSeconds(secondsSetting?.value || "3600");
      setCooldowns(active.cooldowns);
    } catch {
      setMessage("Failed to load cooldown settings.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function saveSettings() {
    setSaving(true);
    setMessage("");
    try {
      await bulkUpdateSettings({
        [LIMIT_KEY]: limit,
        [SECONDS_KEY]: cooldownSeconds,
      });
      setMessage("Cooldown settings saved.");
      await loadAll();
    } catch {
      setMessage("Failed to save cooldown settings.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number) {
    if (!window.confirm("Remove this cooldown?")) return;
    setBusyId(id);
    try {
      await removeCooldown(id);
      setMessage("Cooldown removed.");
      await loadAll();
    } catch {
      setMessage("Failed to remove cooldown.");
    } finally {
      setBusyId(null);
    }
  }

  async function extend(id: number) {
    const seconds = Number(extendSeconds[id] || 0);
    if (seconds <= 0) {
      setMessage("Enter a positive number of seconds to extend.");
      return;
    }
    setBusyId(id);
    try {
      await extendCooldown(id, seconds);
      setExtendSeconds((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setMessage("Cooldown extended.");
      await loadAll();
    } catch {
      setMessage("Failed to extend cooldown.");
    } finally {
      setBusyId(null);
    }
  }

  async function clearExpired() {
    if (!window.confirm("Clear expired cooldowns?")) return;
    setMessage("");
    try {
      const result = await clearExpiredCooldowns();
      setMessage(result.detail);
      await loadAll();
    } catch {
      setMessage("Failed to clear expired cooldowns.");
    }
  }

  if (loading) return <p>Loading cooldowns...</p>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>Cool Down</h1>
          <p style={{ color: "#666", marginTop: 0 }}>
            Control how many deep links a user can open before a temporary block is applied.
          </p>
        </div>
        <button
          onClick={saveSettings}
          disabled={saving}
          style={{
            padding: "10px 18px",
            background: saving ? "#95a5a6" : "#27ae60",
            color: "#fff",
            border: 0,
            borderRadius: 6,
            cursor: saving ? "default" : "pointer",
            fontWeight: 600,
          }}
        >
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>

      {message && (
        <div style={{ padding: 10, margin: "12px 0", background: "#fff", border: "1px solid #ddd", borderRadius: 6 }}>
          {message}
        </div>
      )}

      <section style={{ background: "#fff", padding: 16, border: "1px solid #ddd", borderRadius: 8, marginBottom: 24 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Rule</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
          <label style={{ display: "block", fontWeight: 600 }}>
            Number of links before cooldown
            <input
              type="number"
              min="1"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 6, padding: 8, border: "1px solid #ccc", borderRadius: 4 }}
            />
          </label>
          <label style={{ display: "block", fontWeight: 600 }}>
            Cooldown time in seconds
            <input
              type="number"
              min="1"
              value={cooldownSeconds}
              onChange={(e) => setCooldownSeconds(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 6, padding: 8, border: "1px solid #ccc", borderRadius: 4 }}
            />
          </label>
        </div>
        <p style={{ color: "#666", marginBottom: 0 }}>{currentRule}</p>
      </section>

      <section style={{ background: "#fff", padding: 16, border: "1px solid #ddd", borderRadius: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Active Cooldowns</h2>
          <button
            onClick={clearExpired}
            style={{ padding: "7px 12px", background: "#7f8c8d", color: "#fff", border: 0, borderRadius: 4, cursor: "pointer" }}
          >
            Clear Expired
          </button>
        </div>

        {cooldowns.length === 0 ? (
          <p style={{ color: "#666" }}>No users are currently in cooldown.</p>
        ) : (
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f5f5f5", borderBottom: "2px solid #ddd" }}>
                  <th style={{ padding: 8, textAlign: "left" }}>User</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Links</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Remaining</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Until</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {cooldowns.map((cd) => (
                  <tr key={cd.id} style={{ borderBottom: "1px solid #ddd" }}>
                    <td style={{ padding: 8 }}>
                      <div>{cd.username}</div>
                      <div style={{ color: "#777", fontSize: 11 }}>Telegram ID: {cd.telegram_id}</div>
                    </td>
                    <td style={{ padding: 8 }}>{cd.access_count}</td>
                    <td style={{ padding: 8, fontWeight: 600 }}>{formatSeconds(cd.remaining_seconds)}</td>
                    <td style={{ padding: 8 }}>{new Date(cd.cooldown_until).toLocaleString()}</td>
                    <td style={{ padding: 8 }}>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <input
                          type="number"
                          min="1"
                          placeholder="Seconds"
                          value={extendSeconds[cd.id] || ""}
                          onChange={(e) => setExtendSeconds((prev) => ({ ...prev, [cd.id]: e.target.value }))}
                          style={{ width: 90, padding: 6, border: "1px solid #ccc", borderRadius: 4 }}
                        />
                        <button
                          onClick={() => extend(cd.id)}
                          disabled={busyId === cd.id}
                          style={{ padding: "6px 10px", background: "#3498db", color: "#fff", border: 0, borderRadius: 4, cursor: "pointer" }}
                        >
                          Extend
                        </button>
                        <button
                          onClick={() => remove(cd.id)}
                          disabled={busyId === cd.id}
                          style={{ padding: "6px 10px", background: "#e74c3c", color: "#fff", border: 0, borderRadius: 4, cursor: "pointer" }}
                        >
                          Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
