import { useCallback, useEffect, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import type { PlatformSetting } from "../types";
import { 
  getPlatformSettings, 
  bulkUpdateSettings, 
  triggerLowCreditNotifications,
  getActiveCooldowns,
  removeCooldown,
  extendCooldown,
  clearExpiredCooldowns,
  type CooldownRecord,
} from "../api/endpoints";

const CATEGORIES = ["general", "telegram", "payment", "content", "credits", "notifications", "cooldown"];

const CATEGORY_LABELS: Record<string, string> = {
  general: "🔧 General",
  telegram: "📱 Telegram",
  payment: "💳 Payment",
  content: "📦 Content",
  credits: "🪙 Credits Pricing",
  notifications: "🔔 Notifications",
  cooldown: "🧊 Cool Down",
};

// Human-readable labels for specific setting keys
const FRIENDLY_NAMES: Record<string, string> = {
  content_delete_seconds: "🗑️ Delete Duration (seconds)",
  daily_credits_enabled: "🔄 Daily Free Credits (enabled)",
  daily_credits_amount: "🔄 Daily Free Credits (amount)",
  default_credits_new_user: "🆕 Default Credits for New Users",
  referral_reward_credits: "🎁 Referral Reward Credits",
  referral_enabled: "🎁 Referral Program (enabled)",
  credits_per_inr: "💰 Price per Credit in ₹ (supports decimals)",
  custom_credits_min: "📉 Min Credits per Custom Order",
  custom_credits_max: "📈 Max Credits per Custom Order (0 = no limit)",
  expiry_notify_enabled: "📬 Membership Expiry Reminders (enabled)",
  expiry_notify_days_before: "📅 Days Before Expiry to Notify",
  low_credit_warning_enabled: "⚠️ Low Credit Warnings (enabled)",
  low_credit_thresholds: "📊 Low Credit Warning Thresholds (comma-separated)",
  cooldown_links_limit: "🔗 No of Links for Cooldown",
  cooldown_seconds: "⏱️ Cooldown Time (seconds)",
};

interface Cooldown extends CooldownRecord {}

export default function Settings() {
  const { data: allSettings, loading, error, refetch } = useFetch(
    useCallback(() => getPlatformSettings(), []),
  );

  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [cooldowns, setCooldowns] = useState<Cooldown[]>([]);
  const [loadingCooldowns, setLoadingCooldowns] = useState(false);
  const [extendingId, setExtendingId] = useState<number | null>(null);
  const [extendSeconds, setExtendSeconds] = useState<Record<number, string>>({});

  // Sync fetched settings into local state
  useEffect(() => {
    if (allSettings) {
      const map: Record<string, string> = {};
      allSettings.forEach((s) => {
        map[s.key] = s.value;
      });
      setEditValues(map);
    }
  }, [allSettings]);

  // Load active cooldowns when component mounts or settings update
  useEffect(() => {
    loadCooldowns();
  }, []);

  const loadCooldowns = async () => {
    setLoadingCooldowns(true);
    try {
      const data = await getActiveCooldowns();
      setCooldowns(data.cooldowns);
    } catch (e) {
      console.error("Failed to load cooldowns:", e);
    }
    setLoadingCooldowns(false);
  };

  const handleChange = (key: string, value: string) => {
    setEditValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage("");
    try {
      await bulkUpdateSettings(editValues);
      setMessage("✅ Settings saved successfully!");
      refetch();
      // Reload cooldowns in case limits changed
      loadCooldowns();
    } catch (e) {
      setMessage("❌ Failed to save settings");
    }
    setSaving(false);
  };

  const settingsByCategory = (category: string): PlatformSetting[] => {
    return (allSettings ?? []).filter((s) => s.category === category);
  };

  const handleTriggerLowCredit = async () => {
    setTriggering(true);
    setMessage("");
    try {
      const res = await triggerLowCreditNotifications();
      setMessage(`✅ ${res.detail}`);
    } catch (e) {
      setMessage("❌ Failed to trigger low credit notifications");
    }
    setTriggering(false);
  };

  const handleRemoveCooldown = async (cooldownId: number) => {
    if (!window.confirm("Remove this cooldown?")) return;
    try {
      await removeCooldown(cooldownId);
      setMessage("✅ Cooldown removed");
      await loadCooldowns();
    } catch (e) {
      setMessage("❌ Failed to remove cooldown");
    }
  };

  const handleExtendCooldown = async (cooldownId: number) => {
    const additionalSeconds = parseInt(extendSeconds[cooldownId] || "0", 10);
    if (additionalSeconds <= 0) {
      setMessage("❌ Enter a positive number of seconds");
      return;
    }
    try {
      setExtendingId(cooldownId);
      await extendCooldown(cooldownId, additionalSeconds);
      setMessage(`✅ Cooldown extended by ${additionalSeconds} seconds`);
      setExtendSeconds((prev) => {
        const next = { ...prev };
        delete next[cooldownId];
        return next;
      });
      await loadCooldowns();
    } catch (e) {
      setMessage("❌ Failed to extend cooldown");
    } finally {
      setExtendingId(null);
    }
  };

  const handleClearExpired = async () => {
    if (!window.confirm("Clear all expired cooldowns?")) return;
    try {
      const res = await clearExpiredCooldowns();
      setMessage(`✅ ${res.detail}`);
      await loadCooldowns();
    } catch (e) {
      setMessage("❌ Failed to clear expired cooldowns");
    }
  };

  if (loading) return <p>Loading settings...</p>;

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <h1>⚙️ Platform Settings</h1>
        <div style={{ padding: 16, background: "#f8d7da", borderRadius: 8, color: "#721c24", marginTop: 16 }}>
          <strong>❌ Failed to load settings:</strong> {error}
        </div>
        <button
          onClick={refetch}
          style={{ marginTop: 12, padding: "8px 16px", background: "#3498db", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
        >
          🔄 Retry
        </button>
      </div>
    );
  }

  if (!allSettings || allSettings.length === 0) {
    return (
      <div style={{ padding: 24 }}>
        <h1>⚙️ Platform Settings</h1>
        <div style={{ padding: 16, background: "#fff3cd", borderRadius: 8, color: "#856404", marginTop: 16 }}>
          No settings found. The database may not be initialized yet.
        </div>
        <button
          onClick={refetch}
          style={{ marginTop: 12, padding: "8px 16px", background: "#3498db", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
        >
          🔄 Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>⚙️ Platform Settings</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: "10px 24px",
            background: saving ? "#95a5a6" : "#27ae60",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: saving ? "default" : "pointer",
            fontSize: 15,
            fontWeight: 600,
          }}
        >
          {saving ? "Saving..." : "💾 Save All Settings"}
        </button>
      </div>
      {message && (
        <div style={{ padding: 10, marginBottom: 12, background: message.includes("✅") ? "#d4edda" : "#f8d7da", borderRadius: 4 }}>
          {message}
        </div>
      )}

      <p style={{ color: "#666", margin: "0 0 20px" }}>
        Configure all platform settings here. Changes take effect immediately after saving.
      </p>

      {CATEGORIES.map((cat) => {
        const items = settingsByCategory(cat);
        if (items.length === 0) return null;
        return (
          <div key={cat} style={{ marginBottom: 24 }}>
            <h2 style={{ borderBottom: "2px solid #3498db", paddingBottom: 8, fontSize: 18 }}>
              {CATEGORY_LABELS[cat] || cat}
            </h2>
            <div style={{ background: "#fff", padding: 16, borderRadius: 8, border: "1px solid #ddd" }}>
              {items.map((s) => (
                <div key={s.key} style={{ marginBottom: 16 }}>
                  <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>
                    {FRIENDLY_NAMES[s.key] || s.key}
                  </label>
                  {s.description && (
                    <div style={{ fontSize: 12, color: "#888", marginBottom: 6 }}>{s.description}</div>
                  )}
                  {(s.key.includes("message") || s.key.includes("description")) ? (
                    <textarea
                      value={editValues[s.key] ?? s.value}
                      onChange={(e) => handleChange(s.key, e.target.value)}
                      rows={3}
                      style={{ width: "100%", padding: 8, border: "1px solid #ccc", borderRadius: 4, fontFamily: "inherit" }}
                    />
                  ) : (
                    <input
                      value={editValues[s.key] ?? s.value}
                      onChange={(e) => handleChange(s.key, e.target.value)}
                      autoComplete="off"
                      style={{ width: "100%", padding: 8, border: "1px solid #ccc", borderRadius: 4, fontFamily: s.key.includes("id") || s.key.includes("key") ? "monospace" : "inherit" }}
                    />
                  )}
                </div>
              ))}
              {cat === "notifications" && (
                <div style={{ borderTop: "1px solid #eee", paddingTop: 16, marginTop: 8 }}>
                  <button
                    onClick={handleTriggerLowCredit}
                    disabled={triggering}
                    style={{
                      padding: "10px 20px",
                      background: triggering ? "#95a5a6" : "#e67e22",
                      color: "#fff",
                      border: "none",
                      borderRadius: 6,
                      cursor: triggering ? "default" : "pointer",
                      fontSize: 14,
                      fontWeight: 600,
                    }}
                  >
                    {triggering ? "Sending…" : "⚡ Trigger Low Credit Notifications Now"}
                  </button>
                  <div style={{ fontSize: 12, color: "#888", marginTop: 6 }}>
                    Sends a low-credit warning to ALL users whose balance is at or below the highest threshold. Ignores dedup — useful for testing.
                  </div>
                </div>
              )}
              {cat === "cooldown" && (
                <div style={{ borderTop: "1px solid #eee", paddingTop: 16, marginTop: 8 }}>
                  <h3 style={{ marginTop: 0 }}>🧊 Active Cooldowns</h3>
                  {loadingCooldowns ? (
                    <p>Loading cooldowns...</p>
                  ) : cooldowns.length === 0 ? (
                    <p style={{ color: "#666" }}>No users currently in cooldown.</p>
                  ) : (
                    <>
                      <div style={{ overflowX: "auto", marginBottom: 12 }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                          <thead>
                            <tr style={{ background: "#f5f5f5", borderBottom: "2px solid #ddd" }}>
                              <th style={{ padding: 8, textAlign: "left" }}>User</th>
                              <th style={{ padding: 8, textAlign: "left" }}>Links Accessed</th>
                              <th style={{ padding: 8, textAlign: "left" }}>Remaining Time</th>
                              <th style={{ padding: 8, textAlign: "left" }}>Cooldown Until</th>
                              <th style={{ padding: 8, textAlign: "left" }}>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {cooldowns.map((cd) => (
                              <tr key={cd.id} style={{ borderBottom: "1px solid #ddd" }}>
                                <td style={{ padding: 8 }}>
                                  <div>{cd.username}</div>
                                  <div style={{ fontSize: 11, color: "#888" }}>ID: {cd.telegram_id}</div>
                                </td>
                                <td style={{ padding: 8 }}>{cd.access_count}</td>
                                <td style={{ padding: 8, fontWeight: 600, color: cd.remaining_seconds > 300 ? "#e74c3c" : "#27ae60" }}>
                                  {Math.floor(cd.remaining_seconds / 60)}m {cd.remaining_seconds % 60}s
                                </td>
                                <td style={{ padding: 8, fontSize: 12 }}>{new Date(cd.cooldown_until).toLocaleString()}</td>
                                <td style={{ padding: 8 }}>
                                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                                    <div style={{ display: "flex", gap: 4, width: "100%" }}>
                                      <input
                                        type="number"
                                        value={extendSeconds[cd.id] ?? ""}
                                        onChange={(e) => setExtendSeconds((prev) => ({ ...prev, [cd.id]: e.target.value }))}
                                        placeholder="Sec"
                                        style={{ width: 50, padding: 4, border: "1px solid #ccc", borderRadius: 3, fontSize: 11 }}
                                      />
                                      <button
                                        onClick={() => handleExtendCooldown(cd.id)}
                                        disabled={extendingId === cd.id}
                                        style={{
                                          padding: "4px 8px",
                                          background: extendingId === cd.id ? "#95a5a6" : "#3498db",
                                          color: "#fff",
                                          border: "none",
                                          borderRadius: 3,
                                          cursor: "pointer",
                                          fontSize: 11,
                                        }}
                                      >
                                        {extendingId === cd.id ? "..." : "Extend"}
                                      </button>
                                    </div>
                                    <button
                                      onClick={() => handleRemoveCooldown(cd.id)}
                                      style={{
                                        padding: "4px 12px",
                                        background: "#e74c3c",
                                        color: "#fff",
                                        border: "none",
                                        borderRadius: 3,
                                        cursor: "pointer",
                                        fontSize: 11,
                                      }}
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
                      <button
                        onClick={handleClearExpired}
                        style={{
                          padding: "6px 12px",
                          background: "#95a5a6",
                          color: "#fff",
                          border: "none",
                          borderRadius: 4,
                          cursor: "pointer",
                          fontSize: 12,
                        }}
                      >
                        🗑️ Clear Expired Cooldowns
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}
