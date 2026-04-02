import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { login as apiLogin, logout as apiLogout } from "../api/endpoints";

export function useAuth() {
  const navigate = useNavigate();

  const isAuthenticated = useMemo(
    () => !!localStorage.getItem("admin_token"),
    [],
  );

  const login = useCallback(
    async (username: string, password: string) => {
      await apiLogin(username, password);
      navigate("/dashboard");
    },
    [navigate],
  );

  const logout = useCallback(async () => {
    await apiLogout();
  }, []);

  return { isAuthenticated, login, logout };
}

export default useAuth;