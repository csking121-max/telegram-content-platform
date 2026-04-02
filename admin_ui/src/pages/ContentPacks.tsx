import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import { getContentPacks, deleteContentPack, updateContentPack } from "../api/endpoints";
import type { ContentPack } from "../types";

export default function ContentPacks() {
  const { data: packs, loading, error, refetch } = useFetch(
    useCallback(() => getContentPacks(), []),
  );

  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({
    access_type: "free",
    credit_mode: "per_item",
    credit_cost: 0,
    credit_per_item: 1,
    deletion_seconds: null as number | null,
  });
  const [saving, setSaving] = useState(false);

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this content pack?")) return;
    await deleteContentPack(id);
    refetch();
  };

  const startEdit = (p: ContentPack) => {
    setEditId(p.id);
    setForm({
      access_type: p.access_type,
      credit_mode: p.credit_mode || "per_item",
      credit_cost: p.credit_cost || 0,
      credit_per_item: p.credit_per_item || 1,
      deletion_seconds: p.deletion_seconds,
    });
  };

  const cancelEdit = () => setEditId(null);

  const saveEdit = async () => {
    if (editId === null) return;
    setSaving(true);
    try {
      await updateContentPack(editId, form);
      setEditId(null);
      refetch();
    } catch (e: any) {
      alert("Save failed: " + (e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <>
      <h1>Content Packs</h1>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr>
            <th>ID</th><th>Title</th><th>Access</th><th>Credit Mode</th><th>Cost</th><th>Delete Timer</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {packs?.map((p) => (
            <tr key={p.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{p.id}</td>
              <td>{p.title}</td>
              <td>{p.access_type}</td>
              <td>
                {p.access_type === "credits"
                  ? (p.credit_mode === "per_pack" ? "Per Pack" : "Per Item")
                  : "—"}
              </td>
              <td>
                {p.access_type === "credits"
                  ? p.credit_mode === "per_pack"
                    ? `${p.credit_cost} (flat)`
                    : `${p.credit_per_item || 1}/item`
                  : "—"}
              </td>
              <td>{p.deletion_seconds ? `${p.deletion_seconds}s` : "—"}</td>
              <td>
                <button onClick={() => startEdit(p)} style={{ marginRight: 4 }}>Edit</button>
                <button onClick={() => handleDelete(p.id)} style={{ color: "red" }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Edit Panel */}
      {editId !== null && (
        <div style={{
          marginTop: 20, padding: 20, background: "#f9f9f9",
          border: "1px solid #ddd", borderRadius: 8, maxWidth: 500
        }}>
          <h3>Edit Pack #{editId}</h3>

          <label style={{ display: "block", marginBottom: 8 }}>
            Access Type:
            <select
              value={form.access_type}
              onChange={(e) => setForm({ ...form, access_type: e.target.value })}
              style={{ marginLeft: 8, padding: 4 }}
            >
              <option value="free">Free</option>
              <option value="credits">Credits</option>
              <option value="vip">VIP</option>
              <option value="premium">Premium</option>
              <option value="daily_pass">Daily Pass</option>
            </select>
          </label>

          {form.access_type === "credits" && (
            <>
              <label style={{ display: "block", marginBottom: 8 }}>
                Credit Mode:
                <select
                  value={form.credit_mode}
                  onChange={(e) => setForm({ ...form, credit_mode: e.target.value })}
                  style={{ marginLeft: 8, padding: 4 }}
                >
                  <option value="per_item">Per Item (charge per file)</option>
                  <option value="per_pack">Per Pack (flat charge)</option>
                </select>
              </label>

              {form.credit_mode === "per_pack" ? (
                <label style={{ display: "block", marginBottom: 8 }}>
                  Total Pack Cost (credits):
                  <input
                    type="number" min={1}
                    value={form.credit_cost}
                    onChange={(e) => setForm({ ...form, credit_cost: Number(e.target.value) })}
                    style={{ marginLeft: 8, padding: 4, width: 80 }}
                  />
                </label>
              ) : (
                <label style={{ display: "block", marginBottom: 8 }}>
                  Credits Per Item:
                  <input
                    type="number" min={1}
                    value={form.credit_per_item}
                    onChange={(e) => setForm({ ...form, credit_per_item: Number(e.target.value) })}
                    style={{ marginLeft: 8, padding: 4, width: 80 }}
                  />
                </label>
              )}
            </>
          )}

          <label style={{ display: "block", marginBottom: 12 }}>
            Auto-Delete Timer (seconds, 0 = none):
            <input
              type="number" min={0}
              value={form.deletion_seconds ?? 0}
              onChange={(e) => {
                const v = Number(e.target.value);
                setForm({ ...form, deletion_seconds: v > 0 ? v : null });
              }}
              style={{ marginLeft: 8, padding: 4, width: 80 }}
            />
          </label>

          <button onClick={saveEdit} disabled={saving}
            style={{ marginRight: 8, padding: "6px 16px", background: "#4caf50", color: "#fff", border: "none", borderRadius: 4 }}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button onClick={cancelEdit}
            style={{ padding: "6px 16px", border: "1px solid #ccc", borderRadius: 4 }}>
            Cancel
          </button>
        </div>
      )}
    </>
  );
}