import { Navigate, Outlet } from "react-router-dom";

function isTokenValid(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      localStorage.removeItem("admin_token");
      return false;
    }
    return true;
  } catch {
    localStorage.removeItem("admin_token");
    return false;
  }
}

export default function ProtectedRoute() {
  const token = localStorage.getItem("admin_token");
  if (!token || !isTokenValid(token)) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}