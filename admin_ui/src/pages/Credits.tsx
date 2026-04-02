import { useState } from "react";
import { lookupCreditByTelegram, adjustCredit, getCreditHistory } from "../api/endpoints";
import type { CreditHistory } from "../types";

interface LookupResult {
  user_id: number;
  telegram_id: number;
  username: string | null;
  balance: number;
}

export default function Credits() {
  const [telegramId, setTelegramId] = useState("");
  const [result, setResult] = useState<LookupResult | null>(null);
  const [history, setHistory] = useState<CreditHistory[]>([]);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  const lookup = async () => {
    setError("");
    setResult(null);
    setHistory([]);
    try {
      const r = await lookupCreditByTelegram(Number(telegramId));
      setResult(r);
      try {
        const h = await getCreditHistory(r.user_id);
        setHistory(h);
      } catch { /* history may be empty */ }
    } catch {
      setError("User not found. Make sure you entered a valid Telegram ID.");
    }
  };

  const handleAdjust = async () => {
    if (!result || !amount) return;
    try {
      await adjustCredit(result.user_id, Number(amount), reason || "admin");
      setAmount("");
      setReason("");
      await lookup();            // refresh balance & history
    } catch {
      setError("Adjust failed");
    }
  };

  return (
    <>
      <h1>Credits</h1>

      {/* Lookup form */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
        <input
          placeholder="Telegram ID (e.g. 6189058729)"
          value={telegramId}
          onChange={(e) => setTelegramId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && lookup()}
          style={{ padding: "6px 10px", width: 260, border: "1px solid #ccc", borderRadius: 4 }}
        />
        <button onClick={lookup} style={btnStyle}>Lookup</button>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {result && (
        <div style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <p><strong>DB User ID:</strong> {result.user_id}</p>
            <p><strong>Telegram ID:</strong> {result.telegram_id}</p>
            <p><strong>Username:</strong> @{result.username || "—"}</p>
          </div>
          <p style={{ fontSize: 22, fontWeight: "bold", color: "#4caf50", margin: "8px 0" }}>
            Balance: {result.balance}
          </p>

          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <input
              type="number"
              placeholder="Amount (+/-)"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              style={{ padding: "6px 10px", width: 130, border: "1px solid #ccc", borderRadius: 4 }}
            />
            <input
              placeholder="Reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ padding: "6px 10px", flex: 1, minWidth: 120, border: "1px solid #ccc", borderRadius: 4 }}
            />
            <button onClick={handleAdjust} style={btnStyle}>Adjust</button>
          </div>
          <p style={{ fontSize: 12, color: "#888", margin: "4px 0 0" }}>
            Positive = add credits, negative = deduct credits
          </p>
        </div>
      )}

      {history.length > 0 && (
        <>
          <h3>Credit History</h3>
          <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
            <thead>
              <tr><th style={{textAlign:"left"}}>Amount</th><th style={{textAlign:"left"}}>Reason</th><th style={{textAlign:"left"}}>Date</th></tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td style={{ color: h.change_amount >= 0 ? "#4caf50" : "#f44336", fontWeight: "bold" }}>
                    {h.change_amount >= 0 ? `+${h.change_amount}` : h.change_amount}
                  </td>
                  <td>{h.reason}</td>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "6px 16px", background: "#1976d2", color: "#fff",
  border: "none", borderRadius: 4, cursor: "pointer",
};