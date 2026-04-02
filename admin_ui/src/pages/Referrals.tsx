import { useState } from "react";
import { getReferrals, createInvite } from "../api/endpoints";
import type { Referral } from "../types";

export default function Referrals() {
  const [userId, setUserId] = useState("");
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [error, setError] = useState("");

  const lookup = async () => {
    setError("");
    try {
      const data = await getReferrals(Number(userId));
      setReferrals(data);
    } catch {
      setError("Not found");
    }
  };

  const handleCreate = async () => {
    if (!userId) return;
    await createInvite(Number(userId));
    await lookup();
  };

  return (
    <>
      <h1>Referrals</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="User ID (inviter)" value={userId} onChange={(e) => setUserId(e.target.value)} />
        <button onClick={lookup}>Lookup</button>
        <button onClick={handleCreate}>Create Invite</button>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {referrals.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead>
            <tr><th>Code</th><th>Invitee</th><th>Reward</th><th>Created</th></tr>
          </thead>
          <tbody>
            {referrals.map((r) => (
              <tr key={r.id}>
                <td style={{ fontFamily: "monospace" }}>{r.invite_code}</td>
                <td>{r.used_by_user_id ?? "—"}</td>
                <td>{r.reward_granted ? "✅" : "❌"}</td>
                <td>{new Date(r.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}