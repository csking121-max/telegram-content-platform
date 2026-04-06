import { NavLink } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const links = [
  { to: "/dashboard", label: "📊 Dashboard" },
  { to: "/content-factory", label: "🏭 Content Factory" },
  { to: "/content-manager", label: "📋 Content Manager" },
  { to: "/users", label: "👤 Users" },
  { to: "/bots", label: "🤖 Bots" },
  { to: "/welcome-builder", label: "👋 Welcome Builder" },
  { to: "/content-packs", label: "📦 Content Packs" },
  { to: "/tokens", label: "🔑 Tokens" },
  { to: "/credits", label: "💰 Credits" },
  { to: "/credit-packages", label: "🛒 Credit Packages" },
  { to: "/streaks", label: "🔥 Streaks" },
  { to: "/memberships", label: "🏅 Memberships" },
  { to: "/referrals", label: "🔗 Referrals" },
  { to: "/analytics", label: "📈 Analytics" },
  { to: "/membership-plans", label: "💳 Plans" },
  { to: "/upi-settings", label: "🏦 UPI Settings" },
  { to: "/payments", label: "📋 Payments" },
  { to: "/settings", label: "⚙️ Settings" },
  { to: "/test", label: "🧪 Test Panel" },
  { to: "/logs", label: "📜 Logs" },
  { to: "/dlq", label: "☠️ Dead Letter Queue" },
];

export default function Sidebar() {
  const { logout } = useAuth();

  return (
    <nav
      style={{
        width: 220,
        background: "#1a1a2e",
        color: "#eee",
        padding: "16px 0",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <h2 style={{ textAlign: "center", margin: "0 0 24px" }}>TCAP Admin</h2>

      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          style={({ isActive }) => ({
            display: "block",
            padding: "10px 20px",
            color: isActive ? "#00d2ff" : "#ccc",
            textDecoration: "none",
            fontWeight: isActive ? 600 : 400,
            background: isActive ? "rgba(255,255,255,0.05)" : "transparent",
          })}
        >
          {l.label}
        </NavLink>
      ))}

      <button
        onClick={logout}
        style={{
          marginTop: "auto",
          margin: "24px 20px 16px",
          padding: "8px",
          background: "#e74c3c",
          color: "#fff",
          border: "none",
          borderRadius: 4,
          cursor: "pointer",
        }}
      >
        Logout
      </button>
    </nav>
  );
}