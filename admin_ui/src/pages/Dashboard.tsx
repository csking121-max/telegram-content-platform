import { useCallback, useEffect, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import { getSummary, getHealth, type HealthCheck } from "../api/endpoints";

function HealthWidget() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [error, setError] = useState(false);

  const fetchHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, 15_000);
    return () => clearInterval(id);
  }, [fetchHealth]);

  const dot = (ok: boolean) => (
    <span style={{ color: ok ? "#2ecc71" : "#e74c3c", fontSize: 18, marginRight: 6 }}>●</span>
  );

  if (error) {
    return (
      <div style={{ background: "#fff", borderRadius: 8, padding: "16px 20px", boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: "#888", fontSize: 14 }}>System Health</h3>
        <p style={{ margin: "8px 0 0", color: "#e74c3c" }}>● Unreachable</p>
      </div>
    );
  }

  if (!health) return null;

  return (
    <div style={{ background: "#fff", borderRadius: 8, padding: "16px 20px", boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, color: "#888", fontSize: 14 }}>System Health</h3>
        <span style={{ fontSize: 12, fontWeight: 600, color: health.status === "healthy" ? "#2ecc71" : "#f39c12", textTransform: "uppercase" }}>
          {health.status}
        </span>
      </div>
      <div style={{ display: "flex", gap: 20, marginTop: 10 }}>
        <span>{dot(health.checks.api)} API</span>
        <span>{dot(health.checks.database)} Database</span>
        <span>{dot(health.checks.redis)} Redis</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data, loading, error } = useFetch(useCallback(() => getSummary(), []));

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (!data) return null;

  const cards = [
    { label: "Users", value: data.total_users },
    { label: "Bots", value: data.total_bots },
    { label: "Packs", value: data.total_packs },
    { label: "Deliveries", value: data.total_deliveries },
    { label: "Payments", value: data.total_payments },
  ];

  return (
    <>
      <h1>Dashboard</h1>
      <HealthWidget />
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {cards.map((c) => (
          <div
            key={c.label}
            style={{
              background: "#fff",
              borderRadius: 8,
              padding: "20px 28px",
              minWidth: 150,
              boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
            }}
          >
            <h3 style={{ margin: 0, color: "#888" }}>{c.label}</h3>
            <p style={{ fontSize: 28, margin: "8px 0 0", fontWeight: 700 }}>{c.value}</p>
          </div>
        ))}
      </div>
    </>
  );
}