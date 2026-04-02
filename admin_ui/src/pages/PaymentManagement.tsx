import { useCallback, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import {
  getPaymentOrders,
  getPaymentStats,
  getSmsLogs,
  verifyPaymentOrder,
  rejectPaymentOrder,
  retryPaymentOrder,
} from "../api/endpoints";

type Tab = "orders" | "sms" | "stats";

export default function PaymentManagement() {
  const [tab, setTab] = useState<Tab>("orders");
  const [statusFilter, setStatusFilter] = useState("");

  const {
    data: orders,
    loading: ordLoading,
    refetch: refetchOrders,
  } = useFetch(useCallback(() => getPaymentOrders(statusFilter || undefined), [statusFilter]));

  const { data: stats } = useFetch(useCallback(() => getPaymentStats(), []));
  const { data: smsLogs, loading: smsLoading, refetch: refetchSms } = useFetch(
    useCallback(() => getSmsLogs(), []),
  );

  const handleVerify = async (ref: string) => {
    if (confirm("Admin-verify this payment?")) {
      await verifyPaymentOrder(ref);
      refetchOrders();
    }
  };

  const handleReject = async (ref: string) => {
    if (confirm("Reject this payment order?")) {
      await rejectPaymentOrder(ref);
      refetchOrders();
    }
  };

  const handleRetry = async (ref: string) => {
    if (confirm("Reset this order to pending so the user can retry?")) {
      await retryPaymentOrder(ref);
      refetchOrders();
    }
  };

  const tabStyle = (t: Tab) => ({
    padding: "10px 24px",
    border: "none",
    borderBottom: tab === t ? "3px solid #2980b9" : "3px solid transparent",
    background: "transparent",
    cursor: "pointer" as const,
    fontWeight: tab === t ? 700 : 400,
    fontSize: 15,
  });

  const statusColor: Record<string, string> = {
    pending: "#f39c12",
    utr_submitted: "#2980b9",
    verified: "#27ae60",
    failed: "#e74c3c",
    expired: "#95a5a6",
  };

  return (
    <>
      <h1>Payment Management</h1>

      {/* Stats Row */}
      {stats && (
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          {[
            { label: "Total Orders", value: stats.total_orders, color: "#2c3e50" },
            { label: "Verified", value: stats.verified, color: "#27ae60" },
            { label: "Pending", value: stats.pending, color: "#f39c12" },
            { label: "UTR Submitted", value: stats.utr_submitted, color: "#2980b9" },
            { label: "Failed", value: stats.failed, color: "#e74c3c" },
            { label: "Revenue ₹", value: stats.total_revenue?.toFixed(2) ?? "0.00", color: "#8e44ad" },
          ].map((s) => (
            <div
              key={s.label}
              style={{ flex: 1, background: "#fff", padding: 16, borderRadius: 8, border: "1px solid #ddd", textAlign: "center" }}
            >
              <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ borderBottom: "1px solid #ddd", marginBottom: 16 }}>
        <button style={tabStyle("orders")} onClick={() => setTab("orders")}>Orders</button>
        <button style={tabStyle("sms")} onClick={() => setTab("sms")}>UTR Logs</button>
      </div>

      {/* Orders Tab */}
      {tab === "orders" && (
        <>
          <div style={{ marginBottom: 12 }}>
            <label style={{ marginRight: 8 }}>Filter status:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ padding: 6, borderRadius: 4, border: "1px solid #ccc" }}
            >
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="utr_submitted">UTR Submitted</option>
              <option value="verified">Verified</option>
              <option value="failed">Failed</option>
              <option value="expired">Expired</option>
            </select>
          </div>

          {ordLoading ? (
            <p>Loading...</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f0f0f0" }}>
                  <th style={{ padding: 8, textAlign: "left" }}>Order Ref</th>
                  <th style={{ padding: 8, textAlign: "left" }}>User</th>
                  <th style={{ padding: 8, textAlign: "right" }}>Amount</th>
                  <th style={{ padding: 8, textAlign: "center" }}>Status</th>
                  <th style={{ padding: 8, textAlign: "left" }}>UTR</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Created</th>
                  <th style={{ padding: 8, textAlign: "center" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders?.map((o) => (
                  <tr key={o.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}>{o.order_ref}</td>
                    <td style={{ padding: 8 }}>{o.user_id}</td>
                    <td style={{ padding: 8, textAlign: "right" }}>₹{o.amount}</td>
                    <td style={{ padding: 8, textAlign: "center" }}>
                      <span
                        style={{
                          padding: "2px 10px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          color: "#fff",
                          background: statusColor[o.status] ?? "#999",
                        }}
                      >
                        {o.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}>{o.utr_submitted ?? "-"}</td>
                    <td style={{ padding: 8, fontSize: 11, color: "#888" }}>{new Date(o.created_at).toLocaleString()}</td>
                    <td style={{ padding: 8, textAlign: "center" }}>
                      {(o.status === "pending" || o.status === "utr_submitted") && (
                        <>
                          <button
                            onClick={() => handleVerify(o.order_ref)}
                            style={{ marginRight: 4, padding: "3px 10px", background: "#27ae60", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 11 }}
                          >
                            Verify
                          </button>
                          <button
                            onClick={() => handleReject(o.order_ref)}
                            style={{ padding: "3px 10px", background: "#e74c3c", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 11 }}
                          >
                            Reject
                          </button>
                        </>
                      )}
                      {(o.status === "failed" || o.status === "expired") && (
                        <button
                          onClick={() => handleRetry(o.order_ref)}
                          style={{ padding: "3px 10px", background: "#f39c12", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 11 }}
                        >
                          🔄 Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {(!orders || orders.length === 0) && (
                  <tr><td colSpan={7} style={{ padding: 20, textAlign: "center", color: "#888" }}>No orders found.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </>
      )}

      {/* SMS Logs Tab */}
      {tab === "sms" && (
        <>
          {smsLoading ? (
            <p>Loading...</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f0f0f0" }}>
                  <th style={{ padding: 8, textAlign: "left" }}>ID</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Source</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Message</th>
                  <th style={{ padding: 8, textAlign: "left" }}>UTR Extracted</th>
                  <th style={{ padding: 8, textAlign: "right" }}>Amount</th>
                  <th style={{ padding: 8, textAlign: "center" }}>Matched</th>
                  <th style={{ padding: 8, textAlign: "left" }}>Received</th>
                </tr>
              </thead>
              <tbody>
                {smsLogs?.map((s) => (
                  <tr key={s.id} style={{ borderBottom: "1px solid #eee" }}>
                    <td style={{ padding: 8 }}>{s.id}</td>
                    <td style={{ padding: 8, fontSize: 12 }}>{s.sender}</td>
                    <td style={{ padding: 8, fontSize: 11, maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.body}</td>
                    <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12, fontWeight: 600 }}>{s.utr_extracted ?? "-"}</td>
                    <td style={{ padding: 8, textAlign: "right" }}>{s.amount_extracted ? `₹${s.amount_extracted}` : "-"}</td>
                    <td style={{ padding: 8, textAlign: "center" }}>
                      {s.matched ? (
                        <span style={{ color: "#27ae60", fontWeight: 700 }}>✓</span>
                      ) : (
                        <span style={{ color: "#ccc" }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: 8, fontSize: 11, color: "#888" }}>{new Date(s.received_at).toLocaleString()}</td>
                  </tr>
                ))}
                {(!smsLogs || smsLogs.length === 0) && (
                  <tr><td colSpan={7} style={{ padding: 20, textAlign: "center", color: "#888" }}>No UTR logs yet.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}
