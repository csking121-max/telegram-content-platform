import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** Read a cookie value by name. */
function getCookie(name: string): string | undefined {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // send httpOnly cookies automatically
});

// ── Attach CSRF token + fallback Bearer token ───────────────
apiClient.interceptors.request.use((config) => {
  // CSRF header for cookie-based auth (read from non-httpOnly csrf_token cookie)
  const csrf = getCookie("csrf_token");
  if (csrf && config.headers) {
    config.headers["X-CSRF-Token"] = csrf;
  }
  // Fallback: if the old localStorage token exists, send it as Bearer
  // (transitional — will be removed after all users re-login)
  const legacyToken = localStorage.getItem("admin_token");
  if (legacyToken && config.headers) {
    config.headers.Authorization = `Bearer ${legacyToken}`;
  }
  return config;
});

// ── Redirect to /login on 401 ───────────────────────────────
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("admin_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export default apiClient;