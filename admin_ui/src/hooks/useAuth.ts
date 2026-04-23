import { useCallback, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import { login as apiLogin, logout as apiLogout } from "../api/endpoints";

// Simple external store for token state so all consumers re-render on change
const tokenListeners = new Set<() => void>();
function subscribeToken(cb: () => void) {
  tokenListeners.add(cb);
  return () => { tokenListeners.delete(cb); };
}
function getTokenSnapshot() {
  return localStorage.getItem("admin_token");
}
/** Call after any login/logout to notify all useAuth consumers */
function notifyTokenChange() {
  tokenListeners.forEach((cb) => cb());
}

export function useAuth() {
  const navigate = useNavigate();

  const token = useSyncExternalStore(subscribeToken, getTokenSnapshot);
  const isAuthenticated = !!token;

  const login = useCallback(
    async (username: string, password: string) => {
      await apiLogin(username, password);
      notifyTokenChange();
      navigate("/dashboard");
    },
    [navigate],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    notifyTokenChange();
  }, []);

  return { isAuthenticated, login, logout };
}

export default useAuth;