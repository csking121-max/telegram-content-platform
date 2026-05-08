import { useCallback, useEffect, useMemo, useState } from "react";
import { useFetch } from "../hooks/useFetch";
import {
  getUsers,
  blockUser,
  unblockUser,
  getUserDetail,
  grantUserCredits,
  grantUserMembership,
  setUserLevel,
  revokeMembership,
  getMembershipPlans,
} from "../api/endpoints";
import type { MembershipPlan } from "../types";

interface MembershipInfo {
  id: number;
  membership_type: string;
  start_at: string | null;
  expiry_at: string | null;
  is_active: boolean;
}

interface UserDetail {
  id: number;
  telegram_id: number;
  username: string | null;
  level: number;
  created_at: string | null;
  last_active_at: string | null;
  blocked_until: string | null;
  credit_balance: number;
  memberships: MembershipInfo[];
}

const PAGE_SIZE = 50;

export default function Users() {
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [membershipFilter, setMembershipFilter] = useState("all");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
      setPage(0);
    }, 250);
    return () => window.clearTimeout(t);
  }, [search]);

  const queryParams = useMemo(() => ({
    search: debouncedSearch || undefined,
    status: statusFilter,
    membership: membershipFilter,
    sort_by: sortBy,
    sort_dir: sortDir,
  }), [debouncedSearch, statusFilter, membershipFilter, sortBy, sortDir]);

  const { data: users, loading, error, refetch } = useFetch(
    useCallback(() => getUsers(page * PAGE_SIZE, PAGE_SIZE, queryParams), [page, queryParams]),
  );

  const [selected, setSelected] = useState<UserDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [creditAmt, setCreditAmt] = useState("");
  const [creditReason, setCreditReason] = useState("");
  const [memType, setMemType] = useState("vip");
  const [memDays, setMemDays] = useState("30");
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [newLevel, setNewLevel] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    getMembershipPlans(false).then(setPlans).catch(() => {});
  }, []);

  const loadDetail = async (userId: number) => {
    setLoadingDetail(true);
    setMsg("");
    try {
      const d = await getUserDetail(userId);
      setSelected(d);
      setNewLevel(String(d.level));
    } catch {
      setMsg("Failed to load user details");
    } finally {
      setLoadingDetail(false);
    }
  };

  const toggle = async (id: number, blocked: boolean) => {
    blocked ? await unblockUser(id) : await blockUser(id);
    refetch();
    if (selected?.id === id) loadDetail(id);
  };

  const handleGrantCredits = async () => {
    if (!selected || !creditAmt) return;
    try {
      const res = await grantUserCredits(selected.id, Number(creditAmt), creditReason || "admin");
      setMsg(`Credits updated. New balance: ${res.balance}`);
      setCreditAmt("");
      setCreditReason("");
      loadDetail(selected.id);
      refetch();
    } catch {
      setMsg("Failed to adjust credits");
    }
  };

  const handleGrantMembership = async () => {
    if (!selected) return;
    try {
      const res = await grantUserMembership(selected.id, memType, Number(memDays));
      setMsg(`Granted ${memType} membership until ${res.expiry_at || "forever"}`);
      loadDetail(selected.id);
      refetch();
    } catch {
      setMsg("Failed to grant membership");
    }
  };

  const handleRevokeMembership = async (memId: number) => {
    try {
      await revokeMembership(memId);
      setMsg("Membership revoked");
      if (selected) loadDetail(selected.id);
      refetch();
    } catch {
      setMsg("Failed to revoke membership");
    }
  };

  const handleSetLevel = async () => {
    if (!selected) return;
    try {
      await setUserLevel(selected.id, Number(newLevel));
      setMsg(`Level set to ${newLevel}`);
      loadDetail(selected.id);
      refetch();
    } catch {
      setMsg("Failed to set level");
    }
  };

  const resetFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setMembershipFilter("all");
    setSortBy("created_at");
    setSortDir("desc");
    setPage(0);
  };

  const membershipLabel = (membership?: string | null, count = 0) => {
    if (!membership || count === 0) return "None";
    return count > 1 ? `${membership.toUpperCase()} +${count - 1}` : membership.toUpperCase();
  };

  if (loading) return <p>Loading...</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <div style={{ display: "flex", gap: 24 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h1>Users</h1>

        <div style={toolbarStyle}>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ID, Telegram ID, username"
            style={{ ...inputStyle, flex: "1 1 260px" }}
          />
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }} style={inputStyle}>
            <option value="all">All statuses</option>
            <option value="active">Active only</option>
            <option value="blocked">Blocked only</option>
          </select>
          <select value={membershipFilter} onChange={(e) => { setMembershipFilter(e.target.value); setPage(0); }} style={inputStyle}>
            <option value="all">All memberships</option>
            <option value="active">Any active membership</option>
            <option value="none">No active membership</option>
            {plans.map((p) => (
              <option key={p.id} value={p.access_type}>{p.display_name || p.name}</option>
            ))}
          </select>
          <select value={sortBy} onChange={(e) => { setSortBy(e.target.value); setPage(0); }} style={inputStyle}>
            <option value="created_at">Sort by created</option>
            <option value="last_active_at">Sort by last active</option>
            <option value="id">Sort by ID</option>
            <option value="telegram_id">Sort by Telegram ID</option>
            <option value="username">Sort by username</option>
            <option value="level">Sort by level</option>
            <option value="credit_balance">Sort by credits</option>
            <option value="membership">Sort by membership</option>
            <option value="status">Sort by status</option>
          </select>
          <select value={sortDir} onChange={(e) => { setSortDir(e.target.value as "asc" | "desc"); setPage(0); }} style={inputStyle}>
            <option value="desc">Desc</option>
            <option value="asc">Asc</option>
          </select>
          <button onClick={resetFilters} style={btnSecondary}>Reset</button>
        </div>

        <table style={tableStyle}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Telegram ID</th>
              <th>Username</th>
              <th>Level</th>
              <th>Credits</th>
              <th>Membership</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr
                key={u.id}
                style={{
                  borderBottom: "1px solid #eee",
                  background: selected?.id === u.id ? "#e3f2fd" : undefined,
                  cursor: "pointer",
                }}
                onClick={() => loadDetail(u.id)}
              >
                <td>{u.id}</td>
                <td>{u.telegram_id}</td>
                <td>{u.username ? `@${u.username}` : "-"}</td>
                <td>{u.level}</td>
                <td style={{ fontWeight: 700 }}>{u.credit_balance ?? 0}</td>
                <td>{membershipLabel(u.active_membership, u.active_membership_count)}</td>
                <td>{u.blocked_until ? "Blocked" : "Active"}</td>
                <td>{new Date(u.created_at).toLocaleDateString()}</td>
                <td>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggle(u.id, !!u.blocked_until);
                    }}
                    style={{ marginRight: 4 }}
                  >
                    {u.blocked_until ? "Unblock" : "Block"}
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); loadDetail(u.id); }}>
                    Manage
                  </button>
                </td>
              </tr>
            ))}
            {users?.length === 0 && (
              <tr><td colSpan={9} style={{ padding: 16, color: "#777" }}>No users match these filters.</td></tr>
            )}
          </tbody>
        </table>

        <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} style={btnPrimary}>
            Prev
          </button>
          <span style={{ fontSize: 13 }}>Page {page + 1}</span>
          <button
            disabled={!users || users.length < PAGE_SIZE}
            onClick={() => setPage((p) => p + 1)}
            style={btnPrimary}
          >
            Next
          </button>
        </div>
      </div>

      {selected && (
        <div style={panelStyle}>
          {loadingDetail ? (
            <p>Loading...</p>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h2 style={{ margin: 0 }}>User #{selected.id}</h2>
                <button onClick={() => setSelected(null)} style={closeBtnStyle}>x</button>
              </div>

              {msg && <p style={{ color: "#1976d2", fontSize: 13, margin: "8px 0" }}>{msg}</p>}

              <div style={sectionStyle}>
                <p><strong>Telegram ID:</strong> {selected.telegram_id}</p>
                <p><strong>Username:</strong> @{selected.username || "-"}</p>
                <p><strong>Level:</strong> {selected.level}</p>
                <p><strong>Credits:</strong>{" "}
                  <span style={{ fontSize: 18, fontWeight: "bold", color: "#4caf50" }}>
                    {selected.credit_balance}
                  </span>
                </p>
                <p><strong>Status:</strong> {selected.blocked_until ? "Blocked" : "Active"}</p>
                <p><strong>Created:</strong> {selected.created_at ? new Date(selected.created_at).toLocaleString() : "-"}</p>
                <p><strong>Last Active:</strong> {selected.last_active_at ? new Date(selected.last_active_at).toLocaleString() : "-"}</p>
              </div>

              <div style={sectionStyle}>
                <h4 style={sectionHeader}>Set Level</h4>
                <div style={{ display: "flex", gap: 6 }}>
                  <input type="number" value={newLevel} onChange={(e) => setNewLevel(e.target.value)} style={inputStyle} placeholder="Level" />
                  <button onClick={handleSetLevel} style={btnPrimary}>Set</button>
                </div>
              </div>

              <div style={sectionStyle}>
                <h4 style={sectionHeader}>Credits</h4>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <input
                    type="number"
                    placeholder="Amount (+/-)"
                    value={creditAmt}
                    onChange={(e) => setCreditAmt(e.target.value)}
                    style={{ ...inputStyle, width: 100 }}
                  />
                  <input
                    placeholder="Reason"
                    value={creditReason}
                    onChange={(e) => setCreditReason(e.target.value)}
                    style={{ ...inputStyle, flex: 1, minWidth: 100 }}
                  />
                  <button onClick={handleGrantCredits} style={btnPrimary}>Apply</button>
                </div>
                <p style={{ fontSize: 12, color: "#888", margin: "4px 0 0" }}>
                  Positive = add, negative = deduct
                </p>
              </div>

              <div style={sectionStyle}>
                <h4 style={sectionHeader}>Grant Membership</h4>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <select value={memType} onChange={(e) => setMemType(e.target.value)} style={inputStyle}>
                    {plans.length > 0 ? (
                      plans.map((p) => (
                        <option key={p.access_type} value={p.access_type}>
                          {p.display_name || p.name} ({p.access_type})
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="vip">VIP</option>
                        <option value="premium">Premium</option>
                        <option value="daily_pass">Daily Pass</option>
                      </>
                    )}
                  </select>
                  <input
                    type="number"
                    placeholder="Days"
                    value={memDays}
                    onChange={(e) => setMemDays(e.target.value)}
                    style={{ ...inputStyle, width: 70 }}
                  />
                  <button onClick={handleGrantMembership} style={btnPrimary}>Grant</button>
                </div>
              </div>

              <div style={sectionStyle}>
                <h4 style={sectionHeader}>Memberships</h4>
                {selected.memberships.length === 0 ? (
                  <p style={{ color: "#888", fontSize: 13 }}>No memberships</p>
                ) : (
                  <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                    <thead>
                      <tr><th style={{ textAlign: "left" }}>Type</th><th>Status</th><th>Expires</th><th></th></tr>
                    </thead>
                    <tbody>
                      {selected.memberships.map((m) => (
                        <tr key={m.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                          <td style={{ fontWeight: "bold", textTransform: "uppercase" }}>{m.membership_type}</td>
                          <td>{m.is_active ? "Active" : "Expired"}</td>
                          <td>{m.expiry_at ? new Date(m.expiry_at).toLocaleDateString() : "Forever"}</td>
                          <td>
                            {m.is_active && (
                              <button
                                onClick={() => handleRevokeMembership(m.id)}
                                style={{ color: "red", background: "none", border: "none", cursor: "pointer", fontSize: 12 }}
                              >
                                Revoke
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div style={sectionStyle}>
                <button
                  onClick={() => toggle(selected.id, !!selected.blocked_until)}
                  style={{
                    width: "100%", padding: "8px 16px",
                    background: selected.blocked_until ? "#4caf50" : "#f44336",
                    color: "#fff", border: "none", borderRadius: 4, cursor: "pointer",
                  }}
                >
                  {selected.blocked_until ? "Unblock User" : "Block User"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const toolbarStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
  alignItems: "center",
  marginBottom: 12,
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  background: "#fff",
};

const panelStyle: React.CSSProperties = {
  width: 420, background: "#fff", border: "1px solid #ddd",
  borderRadius: 8, padding: 20, position: "sticky", top: 20,
  maxHeight: "calc(100vh - 40px)", overflowY: "auto",
};

const closeBtnStyle: React.CSSProperties = {
  background: "none", border: "none", fontSize: 18, cursor: "pointer",
};

const sectionStyle: React.CSSProperties = {
  marginTop: 16, paddingTop: 12, borderTop: "1px solid #eee",
};

const sectionHeader: React.CSSProperties = {
  margin: "0 0 8px", fontSize: 14, color: "#555",
};

const inputStyle: React.CSSProperties = {
  padding: "6px 8px", border: "1px solid #ccc", borderRadius: 4, fontSize: 13,
};

const btnPrimary: React.CSSProperties = {
  padding: "6px 14px", background: "#1976d2", color: "#fff",
  border: "none", borderRadius: 4, cursor: "pointer", fontSize: 13,
};

const btnSecondary: React.CSSProperties = {
  padding: "6px 14px", background: "#eee", color: "#222",
  border: "1px solid #ccc", borderRadius: 4, cursor: "pointer", fontSize: 13,
};
