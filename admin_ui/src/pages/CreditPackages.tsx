import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import {
  getCreditPackages,
  createCreditPackage,
  updateCreditPackage,
  deleteCreditPackage,
} from "../api/endpoints";

interface CreditPackage {
  id: number;
  name: string;
  display_name: string;
  description: string;
  credits: number;
  price_inr: number;
  is_active: boolean;
  sort_order: number;
}

const emptyForm = {
  name: "",
  display_name: "",
  description: "",
  credits: 100,
  price_inr: 49,
  is_active: true,
  sort_order: 0,
};

export default function CreditPackages() {
  const { data: packages, loading, error, refetch } = useFetch(
    useCallback(() => getCreditPackages(), []),
  );
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  const handleSubmit = async () => {
    if (editId) {
      await updateCreditPackage(editId, form);
    } else {
      await createCreditPackage(form);
    }
    setForm(emptyForm);
    setEditId(null);
    setShowForm(false);
    refetch();
  };

  const handleEdit = (p: CreditPackage) => {
    setForm({
      name: p.name,
      display_name: p.display_name,
      description: p.description || "",
      credits: p.credits,
      price_inr: p.price_inr,
      is_active: p.is_active,
      sort_order: p.sort_order,
    });
    setEditId(p.id);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (confirm("Delete this credit package?")) {
      await deleteCreditPackage(id);
      refetch();
    }
  };

  const handleToggle = async (p: CreditPackage) => {
    await updateCreditPackage(p.id, { is_active: !p.is_active });
    refetch();
  };

  if (loading) return <p>Loading...</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Credit Packages</h1>
        <button
          onClick={() => { setShowForm(!showForm); setEditId(null); setForm(emptyForm); }}
          style={{ padding: "8px 16px", background: "#2ecc71", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
        >
          {showForm ? "Cancel" : "+ New Package"}
        </button>
      </div>

      {showForm && (
        <div style={{ background: "#1e1e2e", padding: 16, borderRadius: 8, margin: "16px 0" }}>
          <h3>{editId ? "Edit Package" : "Create Package"}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, maxWidth: 600 }}>
            <label>
              Name
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inputStyle} />
            </label>
            <label>
              Display Name
              <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} style={inputStyle} />
            </label>
            <label>
              Credits
              <input type="number" value={form.credits} onChange={(e) => setForm({ ...form, credits: Number(e.target.value) })} style={inputStyle} />
            </label>
            <label>
              Price (INR)
              <input type="number" value={form.price_inr} onChange={(e) => setForm({ ...form, price_inr: Number(e.target.value) })} style={inputStyle} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>
              Description
              <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={inputStyle} />
            </label>
            <label>
              Sort Order
              <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} style={inputStyle} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
              Active
            </label>
          </div>
          <button onClick={handleSubmit} style={{ marginTop: 12, padding: "8px 24px", background: "#3498db", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
            {editId ? "Update" : "Create"}
          </button>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 16 }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #444" }}>
            <th style={thStyle}>ID</th>
            <th style={thStyle}>Name</th>
            <th style={thStyle}>Credits</th>
            <th style={thStyle}>Price</th>
            <th style={thStyle}>Active</th>
            <th style={thStyle}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {(packages || []).map((p: CreditPackage) => (
            <tr key={p.id} style={{ borderBottom: "1px solid #333" }}>
              <td style={tdStyle}>{p.id}</td>
              <td style={tdStyle}>{p.display_name || p.name}</td>
              <td style={tdStyle}>{p.credits}</td>
              <td style={tdStyle}>Rs.{p.price_inr}</td>
              <td style={tdStyle}>
                <button onClick={() => handleToggle(p)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>
                  {p.is_active ? "✅" : "❌"}
                </button>
              </td>
              <td style={tdStyle}>
                <button onClick={() => handleEdit(p)} style={btnStyle}>Edit</button>
                <button onClick={() => handleDelete(p.id)} style={{ ...btnStyle, background: "#e74c3c" }}>Delete</button>
              </td>
            </tr>
          ))}
          {(!packages || packages.length === 0) && (
            <tr><td colSpan={6} style={{ ...tdStyle, textAlign: "center" }}>No credit packages yet</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}

const inputStyle: React.CSSProperties = { display: "block", width: "100%", padding: 6, marginTop: 4, border: "1px solid #555", borderRadius: 4, background: "#2a2a3e", color: "#eee" };
const thStyle: React.CSSProperties = { textAlign: "left", padding: "8px 12px", color: "#aaa" };
const tdStyle: React.CSSProperties = { padding: "8px 12px" };
const btnStyle: React.CSSProperties = { padding: "4px 12px", marginRight: 4, border: "none", borderRadius: 4, cursor: "pointer", background: "#3498db", color: "#fff" };
