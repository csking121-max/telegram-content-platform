import { useCallback, useEffect, useState } from "react";
import {
  getStreakMilestones,
  createStreakMilestone,
  updateStreakMilestone,
  deleteStreakMilestone,
  getUserStreaks,
  resetUserStreak,
  getPlatformSettings,
  bulkUpdateSettings,
  getStreakLevels,
  createStreakLevel,
  updateStreakLevel,
  deleteStreakLevel,
  getStreakMembershipPlans,
  type StreakMilestone,
  type UserStreakRow,
  type StreakLevelRow,
  type MembershipPlanOption,
} from "../api/endpoints";

/* ── Styles ────────────────────────────────────────────── */

const card = {
  background: "#fff",
  borderRadius: 8,
  padding: "20px 24px",
  boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
  marginBottom: 20,
};

const btn = (bg: string) => ({
  padding: "6px 14px",
  background: bg,
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600 as const,
});

const input = {
  padding: "6px 10px",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: 13,
  width: 100,
};

/* ── Component ─────────────────────────────────────────── */

export default function Streaks() {
  // Settings
  const [streakEnabled, setStreakEnabled] = useState("true");
  const [minDailySpend, setMinDailySpend] = useState("5");
  const [settingsLoading, setSettingsLoading] = useState(false);

  // Milestones
  const [milestones, setMilestones] = useState<StreakMilestone[]>([]);
  const [newDays, setNewDays] = useState("");
  const [newBonus, setNewBonus] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editDays, setEditDays] = useState("");
  const [editBonus, setEditBonus] = useState("");
  const [editLabel, setEditLabel] = useState("");

  // User streaks
  const [userStreaks, setUserStreaks] = useState<UserStreakRow[]>([]);
  const [streaksLoading, setStreaksLoading] = useState(false);

  // Levels
  const [levels, setLevels] = useState<StreakLevelRow[]>([]);
  const [membershipPlans, setMembershipPlans] = useState<MembershipPlanOption[]>([]);
  const [newLvl, setNewLvl] = useState("");
  const [newLvlDays, setNewLvlDays] = useState("");
  const [newLvlCredits, setNewLvlCredits] = useState("0");
  const [newLvlPlanId, setNewLvlPlanId] = useState("");
  const [newLvlMemDays, setNewLvlMemDays] = useState("0");
  const [newLvlLabel, setNewLvlLabel] = useState("");
  const [editLvlId, setEditLvlId] = useState<number | null>(null);
  const [editLvl, setEditLvl] = useState("");
  const [editLvlDays, setEditLvlDays] = useState("");
  const [editLvlCredits, setEditLvlCredits] = useState("");
  const [editLvlPlanId, setEditLvlPlanId] = useState("");
  const [editLvlMemDays, setEditLvlMemDays] = useState("");
  const [editLvlLabel, setEditLvlLabel] = useState("");

  // ── Load settings ───────────────────────────────
  const loadSettings = useCallback(async () => {
    try {
      const all = await getPlatformSettings("streak");
      const map: Record<string, string> = {};
      for (const s of all) {
        map[s.key] = s.value;
      }
      setStreakEnabled(map["streak_enabled"] ?? "true");
      setMinDailySpend(map["streak_min_daily_spend"] ?? "5");
    } catch {
      // ignore
    }
  }, []);

  const saveSettings = async () => {
    setSettingsLoading(true);
    try {
      await bulkUpdateSettings({
        streak_enabled: streakEnabled,
        streak_min_daily_spend: minDailySpend,
      });
    } catch {
      alert("Failed to save settings");
    }
    setSettingsLoading(false);
  };

  // ── Load milestones ─────────────────────────────
  const loadMilestones = useCallback(async () => {
    try {
      setMilestones(await getStreakMilestones());
    } catch {
      // ignore
    }
  }, []);

  const handleCreateMilestone = async () => {
    const days = parseInt(newDays);
    const bonus = parseInt(newBonus);
    if (!days || !bonus) return alert("Days and bonus are required");
    try {
      await createStreakMilestone({ days_required: days, bonus_credits: bonus, label: newLabel || undefined });
      setNewDays("");
      setNewBonus("");
      setNewLabel("");
      loadMilestones();
    } catch (e) {
      alert(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  const handleUpdateMilestone = async (id: number) => {
    try {
      await updateStreakMilestone(id, {
        days_required: parseInt(editDays) || undefined,
        bonus_credits: parseInt(editBonus) || undefined,
        label: editLabel || undefined,
      });
      setEditId(null);
      loadMilestones();
    } catch (e) {
      alert(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  const handleDeleteMilestone = async (id: number) => {
    if (!confirm("Delete this milestone?")) return;
    await deleteStreakMilestone(id);
    loadMilestones();
  };

  const handleToggleMilestone = async (m: StreakMilestone) => {
    await updateStreakMilestone(m.id, { is_active: !m.is_active });
    loadMilestones();
  };

  // ── Load user streaks ───────────────────────────
  const loadUserStreaks = useCallback(async () => {
    setStreaksLoading(true);
    try {
      setUserStreaks(await getUserStreaks());
    } catch {
      // ignore
    }
    setStreaksLoading(false);
  }, []);

  const handleResetStreak = async (userId: number) => {
    if (!confirm("Reset this user's streak to 0?")) return;
    await resetUserStreak(userId);
    loadUserStreaks();
  };

  // ── Load levels ─────────────────────────────────
  const loadLevels = useCallback(async () => {
    try {
      setLevels(await getStreakLevels());
    } catch {
      // ignore
    }
  }, []);

  const loadMembershipPlans = useCallback(async () => {
    try {
      setMembershipPlans(await getStreakMembershipPlans());
    } catch {
      // ignore
    }
  }, []);

  const handleCreateLevel = async () => {
    const lvl = parseInt(newLvl);
    const days = parseInt(newLvlDays);
    if (!lvl || !days) return alert("Level number and streak days are required");
    try {
      await createStreakLevel({
        level: lvl,
        streak_days_required: days,
        bonus_credits: parseInt(newLvlCredits) || 0,
        membership_plan_id: newLvlPlanId ? parseInt(newLvlPlanId) : null,
        membership_duration_days: parseInt(newLvlMemDays) || 0,
        label: newLvlLabel || undefined,
      });
      setNewLvl("");
      setNewLvlDays("");
      setNewLvlCredits("0");
      setNewLvlPlanId("");
      setNewLvlMemDays("0");
      setNewLvlLabel("");
      loadLevels();
    } catch (e) {
      alert(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  const handleUpdateLevel = async (id: number) => {
    try {
      await updateStreakLevel(id, {
        level: parseInt(editLvl) || undefined,
        streak_days_required: parseInt(editLvlDays) || undefined,
        bonus_credits: parseInt(editLvlCredits) || 0,
        membership_plan_id: editLvlPlanId ? parseInt(editLvlPlanId) : null,
        membership_duration_days: parseInt(editLvlMemDays) || 0,
        label: editLvlLabel || undefined,
      });
      setEditLvlId(null);
      loadLevels();
    } catch (e) {
      alert(`Failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  const handleDeleteLevel = async (id: number) => {
    if (!confirm("Delete this level?")) return;
    await deleteStreakLevel(id);
    loadLevels();
  };

  const handleToggleLevel = async (lv: StreakLevelRow) => {
    await updateStreakLevel(lv.id, { is_active: !lv.is_active });
    loadLevels();
  };

  const getPlanName = (planId: number | null) => {
    if (!planId) return "—";
    const p = membershipPlans.find((m) => m.id === planId);
    return p ? p.display_name : `Plan #${planId}`;
  };

  // ── Initial load ────────────────────────────────
  useEffect(() => {
    loadSettings();
    loadMilestones();
    loadLevels();
    loadMembershipPlans();
    loadUserStreaks();
  }, [loadSettings, loadMilestones, loadLevels, loadMembershipPlans, loadUserStreaks]);

  return (
    <>
      <h1>🔥 Streak Manager</h1>

      {/* ── Settings Card ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 12px" }}>Streak Settings</h3>
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            Enabled:
            <select
              value={streakEnabled}
              onChange={(e) => setStreakEnabled(e.target.value)}
              style={{ ...input, width: 80 }}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            Min daily spend:
            <input
              type="number"
              value={minDailySpend}
              onChange={(e) => setMinDailySpend(e.target.value)}
              style={{ ...input, width: 70 }}
              min={1}
            />
            credits
          </label>
          <button onClick={saveSettings} disabled={settingsLoading} style={btn("#27ae60")}>
            {settingsLoading ? "Saving..." : "💾 Save"}
          </button>
        </div>
        <p style={{ fontSize: 12, color: "#888", margin: "8px 0 0" }}>
          When enabled, users build streaks by spending at least the minimum credits per day. Consecutive days unlock milestone bonuses.
        </p>
      </div>

      {/* ── Milestones Card ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 12px" }}>Milestone Rewards</h3>
        <p style={{ fontSize: 13, color: "#666", margin: "0 0 12px" }}>
          Define reward tiers. When a user's streak reaches the required days, they automatically receive the bonus credits.
        </p>

        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f8f9fa", textAlign: "left" }}>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Days</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Bonus Credits</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Label</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Active</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {milestones.map((m) => (
              <tr key={m.id} style={{ borderBottom: "1px solid #eee", opacity: m.is_active ? 1 : 0.5 }}>
                {editId === m.id ? (
                  <>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="number" value={editDays} onChange={(e) => setEditDays(e.target.value)} style={{ ...input, width: 60 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="number" value={editBonus} onChange={(e) => setEditBonus(e.target.value)} style={{ ...input, width: 80 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="text" value={editLabel} onChange={(e) => setEditLabel(e.target.value)} style={{ ...input, width: 150 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>{m.is_active ? "✅" : "❌"}</td>
                    <td style={{ padding: "6px 10px", display: "flex", gap: 4 }}>
                      <button onClick={() => handleUpdateMilestone(m.id)} style={btn("#3498db")}>Save</button>
                      <button onClick={() => setEditId(null)} style={btn("#95a5a6")}>Cancel</button>
                    </td>
                  </>
                ) : (
                  <>
                    <td style={{ padding: "6px 10px", fontWeight: 600 }}>{m.days_required} days</td>
                    <td style={{ padding: "6px 10px", fontWeight: 600, color: "#27ae60" }}>+{m.bonus_credits}</td>
                    <td style={{ padding: "6px 10px" }}>{m.label}</td>
                    <td style={{ padding: "6px 10px" }}>
                      <button onClick={() => handleToggleMilestone(m)} style={{ ...btn(m.is_active ? "#27ae60" : "#95a5a6"), padding: "3px 8px" }}>
                        {m.is_active ? "✅" : "❌"}
                      </button>
                    </td>
                    <td style={{ padding: "6px 10px", display: "flex", gap: 4 }}>
                      <button onClick={() => { setEditId(m.id); setEditDays(String(m.days_required)); setEditBonus(String(m.bonus_credits)); setEditLabel(m.label); }} style={btn("#f39c12")}>✏️</button>
                      <button onClick={() => handleDeleteMilestone(m.id)} style={btn("#e74c3c")}>🗑</button>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Add new milestone */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, padding: "10px 0", borderTop: "1px solid #eee" }}>
          <input type="number" placeholder="Days" value={newDays} onChange={(e) => setNewDays(e.target.value)} style={{ ...input, width: 70 }} min={1} />
          <input type="number" placeholder="Bonus" value={newBonus} onChange={(e) => setNewBonus(e.target.value)} style={{ ...input, width: 80 }} min={1} />
          <input type="text" placeholder="Label (optional)" value={newLabel} onChange={(e) => setNewLabel(e.target.value)} style={{ ...input, width: 160 }} />
          <button onClick={handleCreateMilestone} style={btn("#27ae60")}>+ Add Milestone</button>
        </div>
      </div>

      {/* ── Levels Card ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 4px" }}>⭐ Level Rewards</h3>
        <p style={{ fontSize: 13, color: "#666", margin: "0 0 12px" }}>
          Define user levels based on streak count. Each level can award bonus credits, a membership, or both.
          Rewards are granted automatically when the user reaches the required streak days.
        </p>

        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f8f9fa", textAlign: "left" }}>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Level</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Streak Days</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Credits</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Membership</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Mem. Days</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Label</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Active</th>
              <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {levels.map((lv) => (
              <tr key={lv.id} style={{ borderBottom: "1px solid #eee", opacity: lv.is_active ? 1 : 0.5 }}>
                {editLvlId === lv.id ? (
                  <>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="number" value={editLvl} onChange={(e) => setEditLvl(e.target.value)} style={{ ...input, width: 50 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="number" value={editLvlDays} onChange={(e) => setEditLvlDays(e.target.value)} style={{ ...input, width: 60 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="number" value={editLvlCredits} onChange={(e) => setEditLvlCredits(e.target.value)} style={{ ...input, width: 70 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <select value={editLvlPlanId} onChange={(e) => setEditLvlPlanId(e.target.value)} style={{ ...input, width: 140 }}>
                        <option value="">None</option>
                        {membershipPlans.map((p) => (
                          <option key={p.id} value={p.id}>{p.display_name}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="number" value={editLvlMemDays} onChange={(e) => setEditLvlMemDays(e.target.value)} style={{ ...input, width: 60 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <input type="text" value={editLvlLabel} onChange={(e) => setEditLvlLabel(e.target.value)} style={{ ...input, width: 120 }} />
                    </td>
                    <td style={{ padding: "6px 10px" }}>{lv.is_active ? "✅" : "❌"}</td>
                    <td style={{ padding: "6px 10px", display: "flex", gap: 4 }}>
                      <button onClick={() => handleUpdateLevel(lv.id)} style={btn("#3498db")}>Save</button>
                      <button onClick={() => setEditLvlId(null)} style={btn("#95a5a6")}>Cancel</button>
                    </td>
                  </>
                ) : (
                  <>
                    <td style={{ padding: "6px 10px", fontWeight: 700, fontSize: 15 }}>
                      {"⭐".repeat(Math.min(lv.level, 5))} Lv.{lv.level}
                    </td>
                    <td style={{ padding: "6px 10px", fontWeight: 600 }}>{lv.streak_days_required}d</td>
                    <td style={{ padding: "6px 10px", fontWeight: 600, color: lv.bonus_credits > 0 ? "#27ae60" : "#999" }}>
                      {lv.bonus_credits > 0 ? `+${lv.bonus_credits}` : "—"}
                    </td>
                    <td style={{ padding: "6px 10px", color: lv.membership_plan_id ? "#8e44ad" : "#999" }}>
                      {getPlanName(lv.membership_plan_id)}
                    </td>
                    <td style={{ padding: "6px 10px" }}>{lv.membership_duration_days > 0 ? `${lv.membership_duration_days}d` : "—"}</td>
                    <td style={{ padding: "6px 10px" }}>{lv.label}</td>
                    <td style={{ padding: "6px 10px" }}>
                      <button onClick={() => handleToggleLevel(lv)} style={{ ...btn(lv.is_active ? "#27ae60" : "#95a5a6"), padding: "3px 8px" }}>
                        {lv.is_active ? "✅" : "❌"}
                      </button>
                    </td>
                    <td style={{ padding: "6px 10px", display: "flex", gap: 4 }}>
                      <button onClick={() => {
                        setEditLvlId(lv.id);
                        setEditLvl(String(lv.level));
                        setEditLvlDays(String(lv.streak_days_required));
                        setEditLvlCredits(String(lv.bonus_credits));
                        setEditLvlPlanId(lv.membership_plan_id ? String(lv.membership_plan_id) : "");
                        setEditLvlMemDays(String(lv.membership_duration_days));
                        setEditLvlLabel(lv.label);
                      }} style={btn("#f39c12")}>✏️</button>
                      <button onClick={() => handleDeleteLevel(lv.id)} style={btn("#e74c3c")}>🗑</button>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Add new level */}
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 12, padding: "10px 0", borderTop: "1px solid #eee", flexWrap: "wrap" }}>
          <input type="number" placeholder="Lvl" value={newLvl} onChange={(e) => setNewLvl(e.target.value)} style={{ ...input, width: 50 }} min={1} />
          <input type="number" placeholder="Streak Days" value={newLvlDays} onChange={(e) => setNewLvlDays(e.target.value)} style={{ ...input, width: 80 }} min={1} />
          <input type="number" placeholder="Credits" value={newLvlCredits} onChange={(e) => setNewLvlCredits(e.target.value)} style={{ ...input, width: 70 }} min={0} />
          <select value={newLvlPlanId} onChange={(e) => setNewLvlPlanId(e.target.value)} style={{ ...input, width: 140 }}>
            <option value="">No membership</option>
            {membershipPlans.map((p) => (
              <option key={p.id} value={p.id}>{p.display_name}</option>
            ))}
          </select>
          <input type="number" placeholder="Mem. Days" value={newLvlMemDays} onChange={(e) => setNewLvlMemDays(e.target.value)} style={{ ...input, width: 70 }} min={0} />
          <input type="text" placeholder="Label" value={newLvlLabel} onChange={(e) => setNewLvlLabel(e.target.value)} style={{ ...input, width: 120 }} />
          <button onClick={handleCreateLevel} style={btn("#8e44ad")}>+ Add Level</button>
        </div>
      </div>

      {/* ── User Streaks Card ── */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>User Streaks</h3>
          <button onClick={loadUserStreaks} disabled={streaksLoading} style={btn("#3498db")}>
            {streaksLoading ? "⏳" : "🔄"} Refresh
          </button>
        </div>

        {userStreaks.length === 0 ? (
          <p style={{ color: "#999", fontStyle: "italic" }}>No streak data yet. Streaks are created when users start spending credits.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f8f9fa", textAlign: "left" }}>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>User</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Level</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Current</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Longest</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Today Spent</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Last Active</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Bonus Earned</th>
                <th style={{ padding: "8px 10px", borderBottom: "2px solid #dee2e6" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {userStreaks.map((s) => (
                <tr key={s.user_id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "6px 10px" }}>
                    <span style={{ fontFamily: "monospace" }}>{s.telegram_id}</span>
                    {s.username && <span style={{ color: "#888", marginLeft: 6 }}>@{s.username}</span>}
                  </td>
                  <td style={{ padding: "6px 10px", fontWeight: 700, color: "#8e44ad" }}>
                    {s.current_level > 0 ? `⭐ Lv.${s.current_level}` : "—"}
                  </td>
                  <td style={{ padding: "6px 10px", fontWeight: 600 }}>
                    {"🔥".repeat(Math.min(s.current_streak, 5))} {s.current_streak}d
                  </td>
                  <td style={{ padding: "6px 10px" }}>{s.longest_streak}d</td>
                  <td style={{ padding: "6px 10px" }}>{s.today_spent}</td>
                  <td style={{ padding: "6px 10px", fontSize: 12 }}>{s.last_streak_date || "—"}</td>
                  <td style={{ padding: "6px 10px", color: "#27ae60", fontWeight: 600 }}>+{s.total_bonus_earned}</td>
                  <td style={{ padding: "6px 10px" }}>
                    <button onClick={() => handleResetStreak(s.user_id)} style={btn("#e74c3c")}>Reset</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
