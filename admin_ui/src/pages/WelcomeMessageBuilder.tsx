import { useCallback, useEffect, useState, useMemo } from "react";
import { getPlatformSettings, updatePlatformSetting } from "../api/endpoints";

const PLACEHOLDERS = [
  { tag: "{user_name}", description: "User's display name (first name)", example: "John" },
  { tag: "{username}", description: "User's @username (or display name)", example: "@johndoe" },
  { tag: "{platform_name}", description: "Platform name from settings", example: "My Platform" },
  { tag: "{user_id}", description: "User's Telegram numeric ID", example: "123456789" },
];

const DEFAULT_MESSAGE = "👋 Welcome! Choose an option below:";

export default function WelcomeMessageBuilder() {
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [platformName, setPlatformName] = useState("Content Platform");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchSettings = useCallback(async () => {
    try {
      const settings = await getPlatformSettings("telegram");
      for (const s of settings) {
        if (s.key === "bot_welcome_message") setMessage(s.value || DEFAULT_MESSAGE);
        if (s.key === "platform_name") setPlatformName(s.value || "Content Platform");
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const preview = useMemo(() => {
    let text = message;
    text = text.replace(/\{user_name\}/g, "John");
    text = text.replace(/\{username\}/g, "@johndoe");
    text = text.replace(/\{platform_name\}/g, platformName);
    text = text.replace(/\{user_id\}/g, "123456789");
    return `Hey John!\n\nWelcome to **${platformName}**\n\n${text}`;
  }, [message, platformName]);

  const insertPlaceholder = (tag: string) => {
    setMessage((prev) => prev + tag);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await updatePlatformSetting("bot_welcome_message", message);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      alert("Failed to save welcome message");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p>Loading…</p>;

  return (
    <>
      <h1>Welcome Message Builder</h1>
      <p style={{ color: "#666", marginTop: -8 }}>
        Compose the bot welcome message with dynamic placeholders. Changes are applied immediately to the Telegram bot.
      </p>

      <div style={{ display: "flex", gap: 24 }}>
        {/* Editor panel */}
        <div style={{ flex: 1 }}>
          <h3 style={{ marginBottom: 8 }}>Message Template</h3>

          {/* Placeholder buttons */}
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            {PLACEHOLDERS.map((p) => (
              <button
                key={p.tag}
                onClick={() => insertPlaceholder(p.tag)}
                title={p.description}
                style={{
                  background: "#e3f2fd",
                  border: "1px solid #90caf9",
                  borderRadius: 4,
                  padding: "4px 10px",
                  cursor: "pointer",
                  fontSize: 13,
                  fontFamily: "monospace",
                }}
              >
                {p.tag}
              </button>
            ))}
          </div>

          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={8}
            style={{
              width: "100%",
              fontSize: 14,
              padding: 12,
              borderRadius: 6,
              border: "1px solid #ccc",
              fontFamily: "monospace",
              resize: "vertical",
            }}
          />

          <div style={{ marginTop: 8, fontSize: 12, color: "#888" }}>
            Supports Telegram <b>Markdown</b>: *bold*, _italic_, `code`, [links](url)
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                background: "#1976d2",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                padding: "10px 24px",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {saving ? "Saving..." : "Save Welcome Message"}
            </button>
            <button
              onClick={() => setMessage(DEFAULT_MESSAGE)}
              style={{ padding: "10px 16px", cursor: "pointer" }}
            >
              Reset to Default
            </button>
            {saved && (
              <span style={{ color: "#388e3c", fontWeight: 600, alignSelf: "center" }}>
                ✅ Saved!
              </span>
            )}
          </div>
        </div>

        {/* Preview panel */}
        <div style={{ flex: 1 }}>
          <h3 style={{ marginBottom: 8 }}>Preview</h3>
          <div
            style={{
              background: "#0e1621",
              color: "#e0e0e0",
              padding: 20,
              borderRadius: 12,
              fontFamily: "'Segoe UI', sans-serif",
              fontSize: 14,
              lineHeight: 1.5,
              minHeight: 200,
              position: "relative",
            }}
          >
            {/* Telegram-like message bubble */}
            <div
              style={{
                background: "#182533",
                borderRadius: "12px 12px 12px 4px",
                padding: "12px 16px",
                maxWidth: "85%",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {preview.split("\n").map((line, i) => {
                // Very simple Markdown rendering for preview
                let rendered = line;
                rendered = rendered.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
                rendered = rendered.replace(/\*(.+?)\*/g, "<b>$1</b>");
                rendered = rendered.replace(/_(.+?)_/g, "<i>$1</i>");
                rendered = rendered.replace(/`(.+?)`/g, '<code style="background:#0d1117;padding:2px 4px;border-radius:3px">$1</code>');
                return (
                  <span key={i}>
                    {rendered === "" ? <br /> : <span dangerouslySetInnerHTML={{ __html: rendered }} />}
                    {i < preview.split("\n").length - 1 && rendered !== "" && <br />}
                  </span>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: "#546e7a", marginTop: 8, textAlign: "right" }}>
              Telegram Preview (approximate)
            </div>
          </div>

          {/* Placeholder reference */}
          <h3 style={{ marginTop: 24, marginBottom: 8 }}>Available Placeholders</h3>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f5f5f5" }}>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>Placeholder</th>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>Description</th>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>Example</th>
              </tr>
            </thead>
            <tbody>
              {PLACEHOLDERS.map((p) => (
                <tr key={p.tag} style={{ borderTop: "1px solid #eee" }}>
                  <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "#1976d2" }}>{p.tag}</td>
                  <td style={{ padding: "6px 8px" }}>{p.description}</td>
                  <td style={{ padding: "6px 8px", color: "#666" }}>{p.example}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
