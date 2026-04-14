import { useCallback, useEffect, useRef, useState } from "react";
import {
  getTutorials,
  createTutorial,
  updateTutorial,
  deleteTutorial,
  type TutorialItem,
} from "../api/endpoints";

export default function Tutorials() {
  const [tutorials, setTutorials] = useState<TutorialItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newQuestion, setNewQuestion] = useState("");
  const [newSortOrder, setNewSortOrder] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editQuestion, setEditQuestion] = useState("");
  const [editSortOrder, setEditSortOrder] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchTutorials = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getTutorials();
      setTutorials(data);
    } catch {
      setTutorials([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchTutorials();
  }, [fetchTutorials]);

  const handleAdd = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !newQuestion.trim()) {
      alert("Please enter a question and select a video file.");
      return;
    }
    setUploading(true);
    try {
      await createTutorial(file, newQuestion.trim(), newSortOrder);
      setNewQuestion("");
      setNewSortOrder(0);
      setShowAdd(false);
      if (fileRef.current) fileRef.current.value = "";
      fetchTutorials();
    } catch (e) {
      alert(`Failed to create tutorial: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
    setUploading(false);
  };

  const handleUpdate = async (id: number) => {
    try {
      await updateTutorial(id, { question: editQuestion, sort_order: editSortOrder });
      setEditingId(null);
      fetchTutorials();
    } catch {
      alert("Failed to update tutorial");
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this tutorial?")) return;
    try {
      await deleteTutorial(id);
      fetchTutorials();
    } catch {
      alert("Failed to delete tutorial");
    }
  };

  const card: React.CSSProperties = {
    background: "#fff",
    borderRadius: 8,
    padding: 20,
    boxShadow: "0 1px 4px rgba(0,0,0,.08)",
    marginBottom: 16,
  };

  const btn: React.CSSProperties = {
    padding: "8px 16px",
    border: "none",
    borderRadius: 4,
    cursor: "pointer",
    fontWeight: 600,
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>📚 Tutorials</h1>
        <button
          onClick={() => setShowAdd(!showAdd)}
          style={{ ...btn, background: showAdd ? "#e74c3c" : "#3498db", color: "#fff" }}
        >
          {showAdd ? "✕ Cancel" : "+ Add Tutorial"}
        </button>
      </div>

      {showAdd && (
        <div style={card}>
          <h3 style={{ margin: "0 0 12px" }}>Add New Tutorial</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Tutorial Question
              </label>
              <input
                type="text"
                value={newQuestion}
                onChange={(e) => setNewQuestion(e.target.value)}
                placeholder="e.g. How to buy Credits & Membership?"
                style={{ width: "100%", padding: "8px 12px", border: "1px solid #ccc", borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Tutorial Video
              </label>
              <input type="file" accept="video/*" ref={fileRef} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Sort Order
              </label>
              <input
                type="number"
                value={newSortOrder}
                onChange={(e) => setNewSortOrder(Number(e.target.value))}
                style={{ width: 80, padding: "8px 12px", border: "1px solid #ccc", borderRadius: 4 }}
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={uploading}
              style={{ ...btn, background: "#28a745", color: "#fff", alignSelf: "flex-start", opacity: uploading ? 0.6 : 1 }}
            >
              {uploading ? "⏳ Uploading…" : "📤 Upload & Save"}
            </button>
          </div>
        </div>
      )}

      <div style={card}>
        {loading && <p style={{ color: "#888" }}>Loading tutorials…</p>}
        {!loading && tutorials.length === 0 && (
          <p style={{ color: "#999", fontStyle: "italic" }}>No tutorials yet. Click &quot;+ Add Tutorial&quot; to create one.</p>
        )}
        {tutorials.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f8f9fa", textAlign: "left" }}>
                <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>#</th>
                <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Question</th>
                <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Order</th>
                <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Created</th>
                <th style={{ padding: "8px 12px", borderBottom: "2px solid #dee2e6" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tutorials.map((t) => (
                <tr key={t.id}>
                  <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>{t.id}</td>
                  <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>
                    {editingId === t.id ? (
                      <input
                        type="text"
                        value={editQuestion}
                        onChange={(e) => setEditQuestion(e.target.value)}
                        style={{ width: "100%", padding: "4px 8px", border: "1px solid #ccc", borderRadius: 4 }}
                      />
                    ) : (
                      t.question
                    )}
                  </td>
                  <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>
                    {editingId === t.id ? (
                      <input
                        type="number"
                        value={editSortOrder}
                        onChange={(e) => setEditSortOrder(Number(e.target.value))}
                        style={{ width: 60, padding: "4px 8px", border: "1px solid #ccc", borderRadius: 4 }}
                      />
                    ) : (
                      t.sort_order
                    )}
                  </td>
                  <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee", fontSize: 11, color: "#888" }}>
                    {t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td style={{ padding: "6px 12px", borderBottom: "1px solid #eee" }}>
                    <div style={{ display: "flex", gap: 6 }}>
                      {editingId === t.id ? (
                        <>
                          <button
                            onClick={() => handleUpdate(t.id)}
                            style={{ ...btn, padding: "4px 10px", background: "#28a745", color: "#fff", fontSize: 12 }}
                          >
                            ✓ Save
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            style={{ ...btn, padding: "4px 10px", background: "#6c757d", color: "#fff", fontSize: 12 }}
                          >
                            ✕
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => { setEditingId(t.id); setEditQuestion(t.question); setEditSortOrder(t.sort_order); }}
                            style={{ ...btn, padding: "4px 10px", background: "#ffc107", color: "#333", fontSize: 12 }}
                          >
                            ✏️ Edit
                          </button>
                          <button
                            onClick={() => handleDelete(t.id)}
                            style={{ ...btn, padding: "4px 10px", background: "#dc3545", color: "#fff", fontSize: 12 }}
                          >
                            🗑 Delete
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
