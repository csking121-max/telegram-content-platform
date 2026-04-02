import { useCallback } from "react";
import { useFetch } from "../hooks/useFetch";
import { getRecentActivity, getRevenue } from "../api/endpoints";

export default function Analytics() {
  const { data: activity, loading: aLoading } = useFetch(
    useCallback(() => getRecentActivity(), []),
  );
  const { data: revenue, loading: rLoading } = useFetch(
    useCallback(() => getRevenue(), []),
  );

  if (aLoading || rLoading) return <p>Loading…</p>;

  return (
    <>
      <h1>Analytics</h1>

      {revenue && (
        <div style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 16 }}>
          <h3>Revenue</h3>
          <p>Completed payments: {revenue.completed_payments}</p>
          <p>Total: ${revenue.total_revenue?.toFixed(2)}</p>
        </div>
      )}

      <h3>Recent Activity</h3>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
        <thead>
          <tr><th>User</th><th>Action</th><th>Date</th></tr>
        </thead>
        <tbody>
          {(activity as any[])?.map((a: any, i: number) => (
            <tr key={i}>
              <td>{a.user_id}</td>
              <td>{a.action}</td>
              <td>{new Date(a.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}