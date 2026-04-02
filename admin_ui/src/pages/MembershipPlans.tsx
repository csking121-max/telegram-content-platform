import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import {
  getMembershipPlans,
  createMembershipPlan,
  updateMembershipPlan,
  deleteMembershipPlan,
  getPlanMembers,
  extendMembership,
  deactivateMembership,
  removeMembership,
} from "../api/endpoints";
import type { MembershipPlan, PlanMember } from "../types";

const emptyForm = {
  name: "",
  display_name: "",
  description: "",
  access_type: "vip",
  price_inr: 0,
  credit_price: 0,
  duration_days: 30,
  duration_hours: 0,
  credit_reward: 0,
  is_active: true,
  sort_order: 0,
  tier_level: 0,
};

export default function MembershipPlans() {
  const { data: plans, loading, error, refetch } = useFetch(
    useCallback(() => getMembershipPlans(true), []),
  );
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  // Members modal state
  const [membersModalPlan, setMembersModalPlan] = useState<MembershipPlan | null>(null);
  const [members, setMembers] = useState<PlanMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [extendDays, setExtendDays] = useState<Record<number, number>>({});

  const handleSubmit = async () => {
    if (editId) {
      await updateMembershipPlan(editId, form);
    } else {
      await createMembershipPlan(form);
    }
    setForm(emptyForm);
    setEditId(null);
    setShowForm(false);
    refetch();
  };

  const handleEdit = (p: MembershipPlan) => {
    setForm({
      name: p.name,
      display_name: p.display_name,
      description: p.description || "",
      access_type: p.access_type,
      price_inr: p.price_inr,
      credit_price: p.credit_price || 0,
      duration_days: p.duration_days,
      duration_hours: p.duration_hours || 0,
      credit_reward: p.credit_reward,
      is_active: p.is_active,
      sort_order: p.sort_order,
      tier_level: p.tier_level || 0,
    });
    setEditId(p.id);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (confirm("Delete this plan?")) {
      await deleteMembershipPlan(id);
      refetch();
    }
  };

  const handleToggle = async (p: MembershipPlan) => {
    await updateMembershipPlan(p.id, { is_active: !p.is_active });
    refetch();
  };

  const openMembersModal = async (p: MembershipPlan) => {
    setMembersModalPlan(p);
    setMembersLoading(true);
    try {
      const data = await getPlanMembers(p.id);
      setMembers(data);
    } catch {
      setMembers([]);
    }
    setMembersLoading(false);
  };

  const handleExtend = async (membershipId: number) => {
    const days = extendDays[membershipId] || 0;
    if (days <= 0) return;
    await extendMembership(membershipId, days);
    if (membersModalPlan) openMembersModal(membersModalPlan);
    refetch();
  };

  const handleDeactivate = async (membershipId: number) => {
    if (!confirm("Deactivate this membership?")) return;
    await deactivateMembership(membershipId);
    if (membersModalPlan) openMembersModal(membersModalPlan);
    refetch();
  };

  const handleRemove = async (membershipId: number) => {
    if (!confirm("Permanently remove this membership record?")) return;
    await removeMembership(membershipId);
    if (membersModalPlan) openMembersModal(membersModalPlan);
    refetch();
  };

  if (loading) return <p>Loading...</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Membership Plans</h1>
        <button
          onClick={() => { setShowForm(!showForm); setEditId(null); setForm(emptyForm); }}
          style={{ padding: "8px 16px", background: "#27ae60", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
        >
          {showForm ? "Cancel" : "+ New Plan"}
        </button>
      </div>

      {showForm && (
        <div style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 16, border: "1px solid #ddd" }}>
          <h3>{editId ? "Edit Plan" : "Create Plan"}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label>
              Internal Name
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ width: "100%", padding: 6 }} />
            </label>
            <label>
              Display Name
              <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} style={{ width: "100%", padding: 6 }} />
            </label>
            <label>
              Access Type
              <input value={form.access_type} onChange={(e) => setForm({ ...form, access_type: e.target.value })} style={{ width: "100%", padding: 6 }} placeholder="e.g. vip, premium, daily_pass" />
            </label>
            <label>
              Tier Level
              <input type="number" value={form.tier_level} onChange={(e) => setForm({ ...form, tier_level: +e.target.value })} style={{ width: "100%", padding: 6 }} placeholder="0=lowest, higher=more access" />
            </label>
            <label>
              Price (INR)
              <input type="number" value={form.price_inr} onChange={(e) => setForm({ ...form, price_inr: +e.target.value })} style={{ width: "100%", padding: 6 }} />
            </label>
            <label>
              Credit Price
              <input type="number" value={form.credit_price} onChange={(e) => setForm({ ...form, credit_price: +e.target.value })} style={{ width: "100%", padding: 6 }} placeholder="0 = not purchasable with credits" />
            </label>
            <label>
              Duration (days)
              <input type="number" value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: +e.target.value })} style={{ width: "100%", padding: 6 }} />
            </label>
            <label>
              Duration (hours)
              <input type="number" value={form.duration_hours} onChange={(e) => setForm({ ...form, duration_hours: +e.target.value })} style={{ width: "100%", padding: 6 }} placeholder="Extra hours on top of days" />
            </label>
            <label>
              Bonus Credits
              <input type="number" value={form.credit_reward} onChange={(e) => setForm({ ...form, credit_reward: +e.target.value })} style={{ width: "100%", padding: 6 }} />
            </label>
            <label>
              Sort Order
              <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: +e.target.value })} style={{ width: "100%", padding: 6 }} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>
              Description
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={{ width: "100%", padding: 6, minHeight: 60 }} />
            </label>
          </div>
          <button onClick={handleSubmit} style={{ marginTop: 12, padding: "8px 24px", background: "#2980b9", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
            {editId ? "Update" : "Create"}
          </button>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr style={{ background: "#f0f0f0" }}>
            <th style={{ padding: 8, textAlign: "left" }}>ID</th>
            <th style={{ padding: 8, textAlign: "left" }}>Name</th>
            <th style={{ padding: 8, textAlign: "left" }}>Display</th>
            <th style={{ padding: 8, textAlign: "left" }}>Type</th>
            <th style={{ padding: 8, textAlign: "center" }}>Tier</th>
            <th style={{ padding: 8, textAlign: "right" }}>Price (₹)</th>
            <th style={{ padding: 8, textAlign: "right" }}>Credit Price</th>
            <th style={{ padding: 8, textAlign: "right" }}>Duration</th>
            <th style={{ padding: 8, textAlign: "right" }}>Bonus</th>
            <th style={{ padding: 8, textAlign: "center" }}>Active Members</th>
            <th style={{ padding: 8, textAlign: "center" }}>Active</th>
            <th style={{ padding: 8, textAlign: "center" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {plans?.map((p) => (
            <tr key={p.id} style={{ borderBottom: "1px solid #eee", opacity: p.is_active ? 1 : 0.5 }}>
              <td style={{ padding: 8 }}>{p.id}</td>
              <td style={{ padding: 8 }}>{p.name}</td>
              <td style={{ padding: 8 }}>{p.display_name}</td>
              <td style={{ padding: 8 }}><span style={{ background: "#e8f4fd", padding: "2px 8px", borderRadius: 4 }}>{p.access_type}</span></td>
              <td style={{ padding: 8, textAlign: "center" }}>
                <span style={{ background: "#f0e6ff", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>{p.tier_level}</span>
              </td>
              <td style={{ padding: 8, textAlign: "right", fontWeight: 600 }}>₹{p.price_inr}</td>
              <td style={{ padding: 8, textAlign: "right" }}>{p.credit_price || "—"}</td>
              <td style={{ padding: 8, textAlign: "right" }}>{p.duration_days}d {p.duration_hours ? `${p.duration_hours}h` : ""}</td>
              <td style={{ padding: 8, textAlign: "right" }}>{p.credit_reward || "—"}</td>
              <td style={{ padding: 8, textAlign: "center" }}>
                <button
                  onClick={() => openMembersModal(p)}
                  style={{ background: "none", border: "none", color: "#2980b9", cursor: "pointer", fontWeight: 600, textDecoration: "underline", fontSize: 14 }}
                >
                  {p.active_member_count ?? 0}
                </button>
              </td>
              <td style={{ padding: 8, textAlign: "center" }}>
                <button onClick={() => handleToggle(p)} style={{ background: p.is_active ? "#27ae60" : "#95a5a6", color: "#fff", border: "none", borderRadius: 4, padding: "4px 8px", cursor: "pointer" }}>
                  {p.is_active ? "ON" : "OFF"}
                </button>
              </td>
              <td style={{ padding: 8, textAlign: "center" }}>
                <button onClick={() => handleEdit(p)} style={{ marginRight: 4, cursor: "pointer" }}>Edit</button>
                <button onClick={() => handleDelete(p.id)} style={{ color: "red", cursor: "pointer" }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Members Modal */}
      {membersModalPlan && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: 24, maxWidth: 800, width: "90%", maxHeight: "80vh", overflow: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h2 style={{ margin: 0 }}>Active Members — {membersModalPlan.display_name}</h2>
              <button onClick={() => setMembersModalPlan(null)} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer" }}>✕</button>
            </div>

            {membersLoading ? (
              <p>Loading members...</p>
            ) : members.length === 0 ? (
              <p style={{ color: "#999" }}>No active members for this plan.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "#f0f0f0" }}>
                    <th style={{ padding: 8, textAlign: "left" }}>User ID</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Telegram ID</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Username</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Started</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Expires</th>
                    <th style={{ padding: 8, textAlign: "center" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.membership_id} style={{ borderBottom: "1px solid #eee" }}>
                      <td style={{ padding: 8 }}>{m.user_id}</td>
                      <td style={{ padding: 8 }}>{m.telegram_id}</td>
                      <td style={{ padding: 8 }}>{m.username ? `@${m.username}` : "—"}</td>
                      <td style={{ padding: 8 }}>{new Date(m.start_at).toLocaleDateString()}</td>
                      <td style={{ padding: 8 }}>{m.expiry_at ? new Date(m.expiry_at).toLocaleString() : "Lifetime"}</td>
                      <td style={{ padding: 8, textAlign: "center" }}>
                        <div style={{ display: "flex", gap: 4, alignItems: "center", justifyContent: "center", flexWrap: "wrap" }}>
                          <input
                            type="number"
                            placeholder="days"
                            min={1}
                            style={{ width: 50, padding: 2 }}
                            value={extendDays[m.membership_id] || ""}
                            onChange={(e) => setExtendDays({ ...extendDays, [m.membership_id]: +e.target.value })}
                          />
                          <button onClick={() => handleExtend(m.membership_id)} style={{ background: "#2980b9", color: "#fff", border: "none", borderRadius: 3, padding: "3px 8px", cursor: "pointer", fontSize: 12 }}>
                            Extend
                          </button>
                          <button onClick={() => handleDeactivate(m.membership_id)} style={{ background: "#e67e22", color: "#fff", border: "none", borderRadius: 3, padding: "3px 8px", cursor: "pointer", fontSize: 12 }}>
                            Deactivate
                          </button>
                          <button onClick={() => handleRemove(m.membership_id)} style={{ background: "#e74c3c", color: "#fff", border: "none", borderRadius: 3, padding: "3px 8px", cursor: "pointer", fontSize: 12 }}>
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </>
  );
}
