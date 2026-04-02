import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import {
  getUpiConfigs,
  createUpiConfig,
  updateUpiConfig,
  setActiveUpi,
  deleteUpiConfig,
} from "../api/endpoints";

export default function UpiSettings() {
  const { data: configs, loading, error, refetch } = useFetch(
    useCallback(() => getUpiConfigs(), []),
  );
  const [upiId, setUpiId] = useState("");
  const [payeeName, setPayeeName] = useState("");
  const [showForm, setShowForm] = useState(false);

  const handleAdd = async () => {
    if (!upiId.trim() || !payeeName.trim()) return;
    await createUpiConfig({ upi_id: upiId.trim(), payee_name: payeeName.trim() });
    setUpiId("");
    setPayeeName("");
    setShowForm(false);
    refetch();
  };

  const handleSetActive = async (id: number) => {
    await setActiveUpi(id);
    refetch();
  };

  const handleDelete = async (id: number) => {
    if (confirm("Delete this UPI ID?")) {
      await deleteUpiConfig(id);
      refetch();
    }
  };

  if (loading) return <p>Loading...</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>UPI Payment Settings</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{ padding: "8px 16px", background: "#27ae60", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
        >
          {showForm ? "Cancel" : "+ Add UPI ID"}
        </button>
      </div>

      <p style={{ color: "#666", margin: "0 0 16px" }}>
        Manage UPI IDs used for payment QR code generation. Only one can be active at a time.
      </p>

      {showForm && (
        <div style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 16, border: "1px solid #ddd" }}>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <label style={{ flex: 1 }}>
              UPI ID
              <input
                value={upiId}
                onChange={(e) => setUpiId(e.target.value)}
                placeholder="merchant@ybl"
                style={{ width: "100%", padding: 8, border: "1px solid #ccc", borderRadius: 4 }}
              />
            </label>
            <label style={{ flex: 1 }}>
              Payee Name
              <input
                value={payeeName}
                onChange={(e) => setPayeeName(e.target.value)}
                placeholder="Business Name"
                style={{ width: "100%", padding: 8, border: "1px solid #ccc", borderRadius: 4 }}
              />
            </label>
            <button
              onClick={handleAdd}
              style={{ padding: "8px 24px", background: "#2980b9", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", whiteSpace: "nowrap" }}
            >
              Add
            </button>
          </div>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr style={{ background: "#f0f0f0" }}>
            <th style={{ padding: 10, textAlign: "left" }}>ID</th>
            <th style={{ padding: 10, textAlign: "left" }}>UPI ID</th>
            <th style={{ padding: 10, textAlign: "left" }}>Payee Name</th>
            <th style={{ padding: 10, textAlign: "center" }}>Status</th>
            <th style={{ padding: 10, textAlign: "left" }}>Created</th>
            <th style={{ padding: 10, textAlign: "center" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {configs?.map((c) => (
            <tr key={c.id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: 10 }}>{c.id}</td>
              <td style={{ padding: 10, fontFamily: "monospace", fontWeight: 600 }}>{c.upi_id}</td>
              <td style={{ padding: 10 }}>{c.payee_name}</td>
              <td style={{ padding: 10, textAlign: "center" }}>
                {c.is_active ? (
                  <span style={{ background: "#27ae60", color: "#fff", padding: "4px 12px", borderRadius: 4, fontSize: 12 }}>
                    ACTIVE
                  </span>
                ) : (
                  <span style={{ background: "#95a5a6", color: "#fff", padding: "4px 12px", borderRadius: 4, fontSize: 12 }}>
                    INACTIVE
                  </span>
                )}
              </td>
              <td style={{ padding: 10, fontSize: 12, color: "#888" }}>{new Date(c.created_at).toLocaleDateString()}</td>
              <td style={{ padding: 10, textAlign: "center" }}>
                {!c.is_active && (
                  <button
                    onClick={() => handleSetActive(c.id)}
                    style={{ marginRight: 8, padding: "4px 12px", background: "#2980b9", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 12 }}
                  >
                    Set Active
                  </button>
                )}
                <button
                  onClick={() => handleDelete(c.id)}
                  style={{ padding: "4px 12px", color: "red", background: "transparent", border: "1px solid red", borderRadius: 4, cursor: "pointer", fontSize: 12 }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {(!configs || configs.length === 0) && (
            <tr><td colSpan={6} style={{ padding: 20, textAlign: "center", color: "#888" }}>No UPI IDs configured. Add one to start accepting payments.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
