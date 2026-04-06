import { useCallback, useEffect, useState } from "react";
import {
  getFactoryContent,
  getActiveBots,
  deleteContentPack,
  updateContentPack,
  republishContent,
  getFactoryCategories,
} from "../api/endpoints";
import type { Bot, ContentCategory, ContentItem } from "../types";

/* ── styles ────────────────────────────────────────────── */

const card: React.CSSProperties = {
  background: "#fff",
  borderRadius: 8,
  padding: 20,
  boxShadow: "0 1px 3px rgba(0,0,0,.1)",
  marginBottom: 16,
};

const btn: React.CSSProperties = {
  padding: "5px 12px",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 600,
  fontSize: 12,
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "10px 8px",
  borderBottom: "2px solid #ddd",
  fontSize: 13,
  fontWeight: 600,
  color: "#555",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "8px",
  borderBottom: "1px solid #eee",
  verticalAlign: "middle",
  fontSize: 13,
};

const input: React.CSSProperties = {
  padding: "5px 8px",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: 13,
  boxSizing: "border-box",
};

const selectStyle: React.CSSProperties = { ...input };

/* ── component ─────────────────────────────────────────── */

export default function ContentManager() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [categories, setCategories] = useState<ContentCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({
    access_type: "free",
    credit_mode: "per_item",
    credit_cost: 0,
    credit_per_item: 1,
    deletion_seconds: null as number | null,
  });
  const [saving, setSaving] = useState(false);
  const [copiedToken, setCopiedToken] = useState("");
  const [republishBotId, setRepublishBotId] = useState(0);

  const loadContent = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getFactoryContent(0, 200);
      setItems(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load content");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadContent();
    getActiveBots().then((b) => {
      setBots(b);
      if (b.length) setRepublishBotId(b[0].id);
    }).catch(() => {});
    getFactoryCategories().then(setCategories).catch(() => {
      setCategories([
        { tag: "free", label: "Free" },
        { tag: "credits", label: "Credits" },
        { tag: "credits_only", label: "Credits Only" },
      ]);
    });
  }, [loadContent]);

  /* ── actions ────────────────────────────────────── */

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this content pack and all its items?")) return;
    try {
      await deleteContentPack(id);
      setItems((prev) => prev.filter((p) => p.id !== id));
    } catch {
      alert("Delete failed");
    }
  };

  const startEdit = (item: ContentItem) => {
    setEditId(item.id);
    setEditForm({
      access_type: item.access_type,
      credit_mode: item.credit_mode,
      credit_cost: item.credit_cost,
      credit_per_item: item.credit_per_item,
      deletion_seconds: item.deletion_seconds,
    });
  };

  const saveEdit = async () => {
    if (editId === null) return;
    setSaving(true);
    try {
      await updateContentPack(editId, editForm);
      setEditId(null);
      loadContent();
    } catch {
      alert("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleRepublish = async (item: ContentItem) => {
    if (!republishBotId) { alert("Select a bot first"); return; }
    try {
      const res = await republishContent(item.id, republishBotId);
      if (res.posted) {
        alert(`Re-published to channel!\nDeep link: ${res.deep_link}`);
      } else {
        alert(`Channel post failed. Deep link: ${res.deep_link}`);
      }
    } catch {
      alert("Re-publish failed");
    }
  };

  const copyLink = (item: ContentItem) => {
    if (!item.deep_link) return;
    const text = item.deep_link;
    // navigator.clipboard requires HTTPS; use fallback for HTTP
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopiedToken(item.token || "");
    setTimeout(() => setCopiedToken(""), 2000);
  };

  const accessBadge = (type: string) => {
    const colors: Record<string, string> = {
      free: "#2ecc71",
      credits: "#f39c12",
      credits_only: "#e67e22",
      vip: "#9b59b6",
      premium: "#e74c3c",
      daily_pass: "#3498db",
    };
    return (
      <span
        style={{
          display: "inline-block",
          padding: "2px 8px",
          borderRadius: 10,
          fontSize: 11,
          fontWeight: 700,
          color: "#fff",
          background: colors[type] || "#888",
          textTransform: "uppercase",
        }}
      >
        {type}
      </span>
    );
  };

  /* ── render ──────────────────────────────────────── */

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <>
      <h1 style={{ marginBottom: 8 }}>📊 Content Manager</h1>
      <p style={{ color: "#666", marginTop: 0, marginBottom: 20 }}>
        Manage, edit, and re-publish your content packs.
      </p>

      {/* ── Republish Bot selector ── */}
      <div style={{ ...card, display: "flex", alignItems: "center", gap: 12 }}>
        <label style={{ fontWeight: 600, fontSize: 13 }}>Default Bot for Re-publish:</label>
        <select
          value={republishBotId}
          onChange={(e) => setRepublishBotId(Number(e.target.value))}
          style={{ ...selectStyle, width: 180 }}
        >
          {bots.map((b) => (
            <option key={b.id} value={b.id}>@{b.bot_username}</option>
          ))}
        </select>
        <button onClick={loadContent} style={{ ...btn, background: "#4A90E2", color: "#fff" }}>
          ↻ Refresh
        </button>
      </div>

      {/* ── Content Table ── */}
      <div style={{ ...card, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={thStyle}>ID</th>
              <th style={thStyle}>Title</th>
              <th style={thStyle}>Category</th>
              <th style={thStyle}>Price</th>
              <th style={thStyle}>Items</th>
              <th style={thStyle}>Views</th>
              <th style={thStyle}>Created</th>
              <th style={thStyle}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={8} style={{ ...tdStyle, textAlign: "center", color: "#888", padding: 24 }}>
                  No content packs found. Go to Content Factory to create some!
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id}>
                <td style={tdStyle}>{item.id}</td>
                <td style={{ ...tdStyle, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {item.title}
                </td>
                <td style={tdStyle}>{accessBadge(item.access_type)}</td>
                <td style={tdStyle}>
                  {item.access_type === "free"
                    ? "Free"
                    : item.credit_mode === "per_pack"
                      ? `${item.credit_cost} (flat)`
                      : `${item.credit_per_item}/item`}
                </td>
                <td style={tdStyle}>{item.item_count}</td>
                <td style={tdStyle}>{item.views}</td>
                <td style={{ ...tdStyle, whiteSpace: "nowrap", fontSize: 12 }}>
                  {item.created_at ? new Date(item.created_at).toLocaleDateString() : "—"}
                </td>
                <td style={{ ...tdStyle, whiteSpace: "nowrap" }}>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    <button onClick={() => startEdit(item)} style={{ ...btn, background: "#f0f0f0" }}>
                      ✏️ Edit
                    </button>
                    <button onClick={() => handleRepublish(item)} style={{ ...btn, background: "#e8f5e9", color: "#2e7d32" }}>
                      📢 Re-publish
                    </button>
                    {item.deep_link && (
                      <button onClick={() => copyLink(item)} style={{ ...btn, background: "#e3f2fd", color: "#1565c0" }}>
                        {copiedToken === item.token ? "✅ Copied!" : "📋 Copy Link"}
                      </button>
                    )}
                    <button onClick={() => handleDelete(item.id)} style={{ ...btn, background: "#ffebee", color: "#c62828" }}>
                      🗑️ Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Edit Panel ── */}
      {editId !== null && (
        <div style={card}>
          <h3 style={{ margin: "0 0 12px" }}>Edit Pack #{editId}</h3>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Category</label>
              <select
                value={editForm.access_type}
                onChange={(e) => setEditForm({ ...editForm, access_type: e.target.value })}
                style={{ ...selectStyle, width: 180 }}
              >
                {categories.map((c) => (
                  <option key={c.tag} value={c.tag}>{c.label}</option>
                ))}
              </select>
            </div>

            {(editForm.access_type === "credits" || editForm.access_type === "credits_only") && (
              <>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Credit Mode</label>
                  <select
                    value={editForm.credit_mode}
                    onChange={(e) => setEditForm({ ...editForm, credit_mode: e.target.value })}
                    style={{ ...selectStyle, width: 130 }}
                  >
                    <option value="per_item">Per Item</option>
                    <option value="per_pack">Per Pack</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                    {editForm.credit_mode === "per_pack" ? "Pack Cost" : "Cost/Item"}
                  </label>
                  <input
                    type="number"
                    min={0}
                    value={editForm.credit_mode === "per_pack" ? editForm.credit_cost : editForm.credit_per_item}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      if (editForm.credit_mode === "per_pack")
                        setEditForm({ ...editForm, credit_cost: v });
                      else
                        setEditForm({ ...editForm, credit_per_item: v });
                    }}
                    style={{ ...input, width: 80 }}
                  />
                </div>
              </>
            )}

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Auto-Delete (sec)</label>
              <input
                type="number"
                min={0}
                value={editForm.deletion_seconds ?? 0}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setEditForm({ ...editForm, deletion_seconds: v > 0 ? v : null });
                }}
                style={{ ...input, width: 80 }}
              />
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={saveEdit}
                disabled={saving}
                style={{ ...btn, background: "#4caf50", color: "#fff", padding: "6px 18px" }}
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                onClick={() => setEditId(null)}
                style={{ ...btn, background: "#eee", padding: "6px 18px" }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
