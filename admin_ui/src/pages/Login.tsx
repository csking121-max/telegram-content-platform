import { FormEvent, useState } from "react";
import { useAuth } from "../hooks/useAuth";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await login(username, password);
    } catch {
      setError("Invalid credentials");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "#1a1a2e",
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: "#fff",
          padding: 32,
          borderRadius: 8,
          width: 340,
        }}
      >
        <h2 style={{ marginBottom: 16 }}>Admin Login</h2>
        {error && <p style={{ color: "red" }}>{error}</p>}

        <label>Username</label>
        <input
          style={inputStyle}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />

        <label>Password</label>
        <input
          style={inputStyle}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <button type="submit" style={btnStyle}>
          Sign In
        </button>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  padding: 8,
  marginBottom: 12,
  border: "1px solid #ccc",
  borderRadius: 4,
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  width: "100%",
  padding: 10,
  background: "#4A90E2",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 600,
};