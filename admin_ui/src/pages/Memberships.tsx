import { useState } from "react";
import { getMemberships, grantMembership, revokeMembership } from "../api/endpoints";
import type { Membership } from "../types";

export default function Memberships() {
  const [userId, setUserId] = useState("");
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [error, setError] = useState("");

  const [newType, setNewType] = useState("vip");
  const [newExpiry, setNewExpiry] = useState("");

  const lookup = async () => {
    setError("");
    try {
      const data = await getMemberships(Number(userId));
      setMemberships(data);
    } catch {
      setError("Not found");
    }
  };

  const handleGrant = async () => {
    if (!userId || !newExpiry) return;
    await grantMembership({
      user_id: Number(userId),
      membership_type: newType,
      expiry_at: new Date(newExpiry).toISOString(),
    });
    await lookup();
  };

  const handleRevoke = async (id: number) => {
    await revokeMembership(id);
    await lookup();
  };

  return (
    <>
      <h1>Memberships</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="User ID" value={userId} onChange={(e) => setUserId(e.target.value)} />
        <button onClick={lookup}>Lookup</button>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <select value={newType} onChange={(e) => setNewType(e.target.value)}>
          <option value="vip">VIP</option>
          <option value="premium">Premium</option>
          <option value="daily_pass">Daily Pass</option>
        </select>
        <input type="date" value={newExpiry} onChange={(e) => setNewExpiry(e.target.value)} />
        <button onClick={handleGrant}>Grant</button>
      </div>

      {memberships.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead>
            <tr><th>ID</th><th>Type</th><th>Expires</th><th>Started</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {memberships.map((m) => (
              <tr key={m.id}>
                <td>{m.id}</td>
                <td>{m.membership_type}</td>
                <td>{m.expiry_at ? new Date(m.expiry_at).toLocaleDateString() : "Never"}</td>
                <td>{new Date(m.start_at).toLocaleDateString()}</td>
                <td><button onClick={() => handleRevoke(m.id)}>Revoke</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}