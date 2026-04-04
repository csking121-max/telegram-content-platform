import { useCallback, useEffect, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import type { PlatformSetting } from "../types";
import { getPlatformSettings, bulkUpdateSettings } from "../api/endpoints";

const CATEGORIES = ["general", "telegram", "payment", "content", "credits", "notifications"];

const CATEGORY_LABELS: Record<string, string> = {
  general: "🔧 General",
  telegram: "📱 Telegram",
  payment: "💳 Payment",
  content: "📦 Content",
  credits: "🪙 Credits Pricing",
  notifications: "🔔 Notifications",
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
};

export default function Settings() {
  const { data: allSettings, loading, error, refetch } = useFetch(
    useCallback(() => getPlatformSettings(), []),
  );

  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

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
    } catch (e) {
      setMessage("❌ Failed to save settings");
    }
    setSaving(false);
  };

  const settingsByCategory = (category: string): PlatformSetting[] => {
    return (allSettings ?? []).filter((s) => s.category === category);
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
            </div>
          </div>
        );
      })}
    </>
  );
}
