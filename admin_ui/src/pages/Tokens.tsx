import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import { getTokens, createToken, deleteToken } from "../api/endpoints";

export default function Tokens() {
  const { data: tokens, loading, error, refetch } = useFetch(
    useCallback(() => getTokens(), []),
  );
  const [packId, setPackId] = useState("");
  const [singleUse, setSingleUse] = useState(true);

  const handleCreate = async () => {
    if (!packId) return;
    await createToken({ pack_id: Number(packId), single_use: singleUse });
    setPackId("");
    refetch();
  };

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <>
      <h1>Tokens</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="Pack ID" value={packId} onChange={(e) => setPackId(e.target.value)} />
        <label>
          <input type="checkbox" checked={singleUse} onChange={(e) => setSingleUse(e.target.checked)} /> Single use
        </label>
        <button onClick={handleCreate}>Generate Token</button>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr><th>Token</th><th>Pack</th><th>Uses</th><th>Single</th><th>Expires</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {tokens?.map((t) => (
            <tr key={t.token}>
              <td style={{ fontFamily: "monospace", fontSize: 12 }}>{t.token}</td>
              <td>{t.pack_id}</td>
              <td>{t.used_count}</td>
              <td>{t.single_use ? "Yes" : "No"}</td>
              <td>{t.expires_at ? new Date(t.expires_at).toLocaleDateString() : "♾️ Never"}</td>
              <td><button onClick={() => deleteToken(t.token).then(refetch)}>Revoke</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}