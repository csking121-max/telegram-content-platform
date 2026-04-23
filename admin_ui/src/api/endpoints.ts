import apiClient from "./client";
import type {
  Bot,
  ContentPack,
  Credit,
  CreditHistory,
  DashboardSummary,
  LoginResponse,
  Membership,
  MembershipPlan,
  PaymentOrder,
  PaymentStats,
  PlanMember,
  PlatformSetting,
  Referral,
  SmsLog,
  Token,
  UpiConfig,
  User,
  ContentCategory,
  ContentItem,
  PublishJob,
} from "../types";

/* ── Auth ──────────────────────────────────────────────────── */

export const login = async (username: string, password: string) => {
  const { data } = await apiClient.post<LoginResponse>("/auth/login", {
    username,
    password,
  });
  // JWT is now set as httpOnly cookie by the server.
  // Keep localStorage as fallback for immediate session detection.
  localStorage.setItem("admin_token", data.access_token);
  return data;
};

export const logout = async () => {
  try {
    await apiClient.post("/auth/logout");
  } catch {
    // ignore errors on logout
  }
  localStorage.removeItem("admin_token");
  window.location.href = "/login";
};

/* ── Dashboard ─────────────────────────────────────────────── */

export const getSummary = () =>
  apiClient.get<DashboardSummary>("/admin/analytics/summary").then((r) => r.data);

/* ── Users ─────────────────────────────────────────────────── */

export const getUsers = (skip = 0, limit = 50) =>
  apiClient.get<User[]>("/admin/users", { params: { skip, limit } }).then((r) => r.data);

export const getUser = (id: number) =>
  apiClient.get<User>(`/admin/users/${id}`).then((r) => r.data);

export const blockUser = (id: number) =>
  apiClient.post<User>(`/admin/users/${id}/block`).then((r) => r.data);

export const unblockUser = (id: number) =>
  apiClient.post<User>(`/admin/users/${id}/unblock`).then((r) => r.data);

export const getUserDetail = (id: number) =>
  apiClient.get(`/admin/users/${id}/detail`).then((r) => r.data);

export const grantUserCredits = (userId: number, amount: number, reason: string) =>
  apiClient.post(`/admin/users/${userId}/grant-credits`, { amount, reason }).then((r) => r.data);

export const grantUserMembership = (userId: number, membership_type: string, days: number) =>
  apiClient.post(`/admin/users/${userId}/grant-membership`, { membership_type, days }).then((r) => r.data);

export const setUserLevel = (userId: number, level: number) =>
  apiClient.post(`/admin/users/${userId}/set-level`, { level }).then((r) => r.data);

/* ── Bots ──────────────────────────────────────────────────── */

export const getBots = (skip = 0, limit = 50) =>
  apiClient.get<Bot[]>("/admin/bots", { params: { skip, limit } }).then((r) => r.data);

export const createBot = (data: { bot_username: string; bot_token: string; webhook_secret: string }) =>
  apiClient.post<Bot>("/admin/bots", data).then((r) => r.data);

export const deleteBot = (id: number) =>
  apiClient.delete(`/admin/bots/${id}`);

export const updateBot = (id: number, data: { cleanup_hours?: number; status?: string }) =>
  apiClient.patch<Bot>(`/admin/bots/${id}`, data).then((r) => r.data);

export const announceBot = (id: number, message: string) =>
  apiClient.post(`/admin/bots/${id}/announce`, { message }).then((r) => r.data);

export const clearBotMessages = (id: number) =>
  apiClient.post(`/admin/bots/${id}/clear-messages`).then((r) => r.data);

export const sendBotWelcome = (id: number) =>
  apiClient.post(`/admin/bots/${id}/send-welcome`).then((r) => r.data);

export const bulkAnnounce = (bot_ids: number[], message: string) =>
  apiClient.post('/admin/bots/bulk/announce', { bot_ids, message }).then((r) => r.data);

export const bulkClearMessages = (bot_ids: number[]) =>
  apiClient.post('/admin/bots/bulk/clear-messages', { bot_ids }).then((r) => r.data);

export const bulkSendWelcome = (bot_ids: number[]) =>
  apiClient.post('/admin/bots/bulk/send-welcome', { bot_ids }).then((r) => r.data);

export const bulkDeleteBots = (bot_ids: number[]) =>
  apiClient.post('/admin/bots/bulk/delete', { bot_ids }).then((r) => r.data);

/* ── Content Packs ─────────────────────────────────────────── */

export const getContentPacks = (skip = 0, limit = 50) =>
  apiClient.get<ContentPack[]>("/admin/content-packs", { params: { skip, limit } }).then((r) => r.data);

export const createContentPack = (data: Partial<ContentPack>) =>
  apiClient.post<ContentPack>("/admin/content-packs", data).then((r) => r.data);

export const updateContentPack = (id: number, data: Partial<ContentPack>) =>
  apiClient.patch<ContentPack>(`/admin/content-packs/${id}`, data).then((r) => r.data);

export const deleteContentPack = (id: number) =>
  apiClient.delete(`/admin/content-packs/${id}`);

/* ── Tokens ────────────────────────────────────────────────── */

export const getTokens = (skip = 0, limit = 50) =>
  apiClient.get<Token[]>("/admin/tokens", { params: { skip, limit } }).then((r) => r.data);

export const createToken = (data: { pack_id: number; single_use?: boolean; expires_at?: string }) =>
  apiClient.post<Token>("/admin/tokens", data).then((r) => r.data);

export const deleteToken = (token: string) =>
  apiClient.delete(`/admin/tokens/${token}`);

/* ── Credits ───────────────────────────────────────────────── */

export const getCredit = (userId: number) =>
  apiClient.get<Credit>(`/admin/credits/${userId}`).then((r) => r.data);

export const lookupCreditByTelegram = (telegramId: number) =>
  apiClient.get(`/admin/credits/lookup`, { params: { telegram_id: telegramId } }).then((r) => r.data);

export const adjustCredit = (userId: number, change_amount: number, reason: string) =>
  apiClient.post<Credit>("/admin/credits/adjust", { user_id: userId, change_amount, reason }).then((r) => r.data);

export const getCreditHistory = (userId: number) =>
  apiClient.get<CreditHistory[]>(`/admin/credits/${userId}/history`).then((r) => r.data);

/* ── Memberships ───────────────────────────────────────────── */

export const getMemberships = (userId: number) =>
  apiClient.get<Membership[]>(`/admin/memberships/${userId}`).then((r) => r.data);

export const grantMembership = (data: { user_id: number; membership_type: string; expiry_at?: string }) =>
  apiClient.post<Membership>("/admin/memberships", data).then((r) => r.data);

export const revokeMembership = (id: number) =>
  apiClient.post<Membership>(`/admin/memberships/${id}/revoke`).then((r) => r.data);

/* ── Referrals ─────────────────────────────────────────────── */

export const getReferrals = (userId: number) =>
  apiClient.get<Referral[]>(`/admin/referrals/user/${userId}`).then((r) => r.data);

export const createInvite = (inviterId: number) =>
  apiClient.post<Referral>("/admin/referrals", { inviter_id: inviterId }).then((r) => r.data);

/* ── Analytics ─────────────────────────────────────────────── */

export interface HealthCheck {
  status: "healthy" | "degraded";
  checks: {
    api: boolean;
    database: boolean;
    redis: boolean;
  };
}

export const getHealth = () =>
  apiClient.get<HealthCheck>("/health").then((r) => r.data);

export const getRecentActivity = (skip = 0, limit = 50) =>
  apiClient.get("/admin/analytics/activity", { params: { skip, limit } }).then((r) => r.data);

export const getRevenue = () =>
  apiClient.get("/admin/analytics/revenue").then((r) => r.data);

/* ── Membership Plans ──────────────────────────────────── */

export const getMembershipPlans = (includeInactive = true) =>
  apiClient.get<MembershipPlan[]>("/admin/membership-plans", { params: { include_inactive: includeInactive } }).then((r) => r.data);

export const getMembershipPlan = (id: number) =>
  apiClient.get<MembershipPlan>(`/admin/membership-plans/${id}`).then((r) => r.data);

export const createMembershipPlan = (data: Partial<MembershipPlan>) =>
  apiClient.post<MembershipPlan>("/admin/membership-plans", data).then((r) => r.data);

export const updateMembershipPlan = (id: number, data: Partial<MembershipPlan>) =>
  apiClient.patch<MembershipPlan>(`/admin/membership-plans/${id}`, data).then((r) => r.data);

export const deleteMembershipPlan = (id: number) =>
  apiClient.delete(`/admin/membership-plans/${id}`);

export const getPlanMembers = (planId: number) =>
  apiClient.get<PlanMember[]>(`/admin/membership-plans/${planId}/members`).then((r) => r.data);

export const extendMembership = (membershipId: number, days: number, hours: number = 0) =>
  apiClient.post(`/admin/membership-plans/members/${membershipId}/extend`, { days, hours }).then((r) => r.data);

export const deactivateMembership = (membershipId: number) =>
  apiClient.post(`/admin/membership-plans/members/${membershipId}/deactivate`).then((r) => r.data);

export const removeMembership = (membershipId: number) =>
  apiClient.delete(`/admin/membership-plans/members/${membershipId}`).then((r) => r.data);

/* ── UPI Config ────────────────────────────────────────── */

export const getUpiConfigs = () =>
  apiClient.get<UpiConfig[]>("/admin/upi-config").then((r) => r.data);

export const createUpiConfig = (data: { upi_id: string; payee_name: string; is_active?: boolean }) =>
  apiClient.post<UpiConfig>("/admin/upi-config", data).then((r) => r.data);

export const updateUpiConfig = (id: number, data: Partial<UpiConfig>) =>
  apiClient.patch<UpiConfig>(`/admin/upi-config/${id}`, data).then((r) => r.data);

export const setActiveUpi = (id: number) =>
  apiClient.post<UpiConfig>(`/admin/upi-config/${id}/set-active`).then((r) => r.data);

export const deleteUpiConfig = (id: number) =>
  apiClient.delete(`/admin/upi-config/${id}`);

/* ── Payment Management ────────────────────────────────── */

export const getPaymentOrders = (status?: string, skip = 0, limit = 50) =>
  apiClient.get<PaymentOrder[]>("/admin/payment-mgmt/orders", { params: { status, skip, limit } }).then((r) => r.data);

export const getPaymentOrder = (orderRef: string) =>
  apiClient.get<PaymentOrder>(`/admin/payment-mgmt/orders/${orderRef}`).then((r) => r.data);

export const verifyPaymentOrder = (orderRef: string) =>
  apiClient.post(`/admin/payment-mgmt/orders/${orderRef}/verify`).then((r) => r.data);

export const rejectPaymentOrder = (orderRef: string) =>
  apiClient.post(`/admin/payment-mgmt/orders/${orderRef}/reject`).then((r) => r.data);

export const retryPaymentOrder = (orderRef: string) =>
  apiClient.post(`/admin/payment-mgmt/orders/${orderRef}/retry`).then((r) => r.data);

export const getPaymentStats = () =>
  apiClient.get<PaymentStats>("/admin/payment-mgmt/stats").then((r) => r.data);

/* ── SMS Logs ──────────────────────────────────────────── */

export const getSmsLogs = (unmatchedOnly = false, limit = 50) =>
  apiClient.get<SmsLog[]>("/admin/payment-mgmt/sms", { params: { unmatched_only: unmatchedOnly, limit } }).then((r) => r.data);

/* ── Platform Settings ─────────────────────────────────── */

export const getPlatformSettings = (category?: string) =>
  apiClient.get<PlatformSetting[]>("/admin/settings", { params: { category } }).then((r) => r.data);

export const updatePlatformSetting = (key: string, value: string) =>
  apiClient.put<PlatformSetting>(`/admin/settings/${key}`, { value }).then((r) => r.data);

export const bulkUpdateSettings = (settings: Record<string, string>) =>
  apiClient.post("/admin/settings/bulk", { settings }).then((r) => r.data);

export const deletePlatformSetting = (key: string) =>
  apiClient.delete(`/admin/settings/${key}`);

/* ── Notifications ─────────────────────────────────────── */

export const triggerLowCreditNotifications = () =>
  apiClient.post<{ detail: string; sent: number; failed: number; total_qualifying: number }>("/admin/notifications/trigger-low-credit").then((r) => r.data);

/* ── Cooldowns ─────────────────────────────────────────── */

export interface CooldownRecord {
  id: number;
  user_id: number;
  telegram_id: number;
  username: string;
  access_count: number;
  exceeded_at: string;
  cooldown_until: string;
  remaining_seconds: number;
  reason: string;
}

export const getActiveCooldowns = () =>
  apiClient.get<{ cooldowns: CooldownRecord[]; total: number }>("/admin/cooldowns").then((r) => r.data);

export const removeCooldown = (cooldownId: number) =>
  apiClient.delete(`/admin/cooldowns/${cooldownId}`).then((r) => r.data);

export const extendCooldown = (cooldownId: number, additionalSeconds: number) =>
  apiClient.post(`/admin/cooldowns/${cooldownId}/extend`, { additional_seconds: additionalSeconds }).then((r) => r.data);

export const clearExpiredCooldowns = () =>
  apiClient.post<{ detail: string }>("/admin/cooldowns/clear-expired").then((r) => r.data);

/* ── Test Panel ────────────────────────────────────────── */

export interface TestResult {
  name: string;
  success: boolean;
  message: string;
  details: Record<string, unknown> | null;
  duration_ms: number | null;
}

export const runAllTests = () =>
  apiClient.post<TestResult[]>("/admin/test/run-all").then((r) => r.data);

export const testPing = () =>
  apiClient.post<TestResult>("/admin/test/ping").then((r) => r.data);

export const testDatabase = () =>
  apiClient.post<TestResult>("/admin/test/database").then((r) => r.data);

export const testSettings = () =>
  apiClient.post<TestResult>("/admin/test/settings").then((r) => r.data);

export const testBotStatus = () =>
  apiClient.post<TestResult>("/admin/test/bot-status").then((r) => r.data);

export const testUtrGroup = () =>
  apiClient.post<TestResult>("/admin/test/utr-group").then((r) => r.data);

export const testUpiConfig = () =>
  apiClient.post<TestResult>("/admin/test/upi-config").then((r) => r.data);

export const testUtrExtraction = (sampleText: string) =>
  apiClient.post<TestResult>("/admin/test/utr-extract", { sample_text: sampleText }).then((r) => r.data);

/* ── Logs ──────────────────────────────────────────────── */

export interface LogSource {
  name: string;
  filename: string;
  exists: boolean;
  size_bytes: number;
  size_human: string;
}

export interface LogResponse {
  source: string;
  filename: string;
  total_lines: number;
  lines: string[];
  file_size_bytes: number;
}

export const getLogSources = () =>
  apiClient.get<LogSource[]>("/admin/logs/sources").then((r) => r.data);

export const getLogs = (source: string, tail = 200, search = "", level = "") =>
  apiClient.get<LogResponse>(`/admin/logs/${source}`, {
    params: { tail, search: search || undefined, level: level || undefined },
  }).then((r) => r.data);

export const clearLog = (source: string) =>
  apiClient.delete(`/admin/logs/${source}`).then((r) => r.data);

/* ── Rate Limits ───────────────────────────────────────── */

export interface RateLimitEntry {
  key: string;
  count: number;
  limit: number;
  remaining: number;
  exceeded: boolean;
  ttl_seconds: number;
}

export interface RateLimitsResponse {
  total_tracked: number;
  entries: RateLimitEntry[];
}

export const getActiveRateLimits = () =>
  apiClient.get<RateLimitsResponse>("/admin/logs/rate-limits/active").then((r) => r.data);

/* ── Bug Reports ───────────────────────────────────────────── */

export interface BugReportItem {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  report: string;
  status: string;
  created_at: string | null;
}

export interface BugReportsResponse {
  total: number;
  items: BugReportItem[];
}

export const getBugReports = (status = "", limit = 100, offset = 0) =>
  apiClient.get<BugReportsResponse>("/admin/bug-reports", {
    params: { status: status || undefined, limit, offset },
  }).then((r) => r.data);

export const updateBugReportStatus = (id: number, status: string) =>
  apiClient.put(`/admin/bug-reports/${id}`, { status }).then((r) => r.data);

/* ── Tutorials ─────────────────────────────────────────────── */

export interface TutorialItem {
  id: number;
  question: string;
  storage_chat_id: number;
  storage_message_id: number;
  file_id: string;
  sort_order: number;
  created_at: string | null;
}

export const getTutorials = () =>
  apiClient.get<TutorialItem[]>("/admin/tutorials").then((r) => r.data);

export const createTutorial = (file: File, question: string, sortOrder = 0) => {
  const fd = new FormData();
  fd.append("file", file);
  const sizeMB = file.size / (1024 * 1024);
  const timeoutMs = Math.max(120_000, Math.ceil(sizeMB / 10) * 60_000);
  return apiClient
    .post(`/admin/tutorials?question=${encodeURIComponent(question)}&sort_order=${sortOrder}`, fd, {
      headers: { "Content-Type": undefined },
      timeout: timeoutMs,
    })
    .then((r) => r.data);
};

export const updateTutorial = (id: number, data: { question?: string; sort_order?: number }) =>
  apiClient.put(`/admin/tutorials/${id}`, data).then((r) => r.data);

export const deleteTutorial = (id: number) =>
  apiClient.delete(`/admin/tutorials/${id}`).then((r) => r.data);

/* -- Credit Packages ---------------------------------------- */

export const getCreditPackages = () =>
  apiClient.get("/admin/credit-packages").then((r) => r.data);

export const createCreditPackage = (data: Record<string, unknown>) =>
  apiClient.post("/admin/credit-packages", data).then((r) => r.data);

export const updateCreditPackage = (id: number, data: Record<string, unknown>) =>
  apiClient.patch(`/admin/credit-packages/${id}`, data).then((r) => r.data);

export const deleteCreditPackage = (id: number) =>
  apiClient.delete(`/admin/credit-packages/${id}`);

/* ── Streaks ───────────────────────────────────────────── */

export interface StreakMilestone {
  id: number;
  days_required: number;
  bonus_credits: number;
  label: string;
  is_active: boolean;
}

export interface UserStreakRow {
  user_id: number;
  telegram_id: number;
  username: string | null;
  current_streak: number;
  longest_streak: number;
  today_spent: number;
  last_streak_date: string | null;
  total_bonus_earned: number;
  last_milestone_claimed: number;
  current_level: number;
}

export const getStreakMilestones = () =>
  apiClient.get<StreakMilestone[]>("/admin/streaks/milestones").then((r) => r.data);

export const createStreakMilestone = (data: { days_required: number; bonus_credits: number; label?: string; is_active?: boolean }) =>
  apiClient.post<StreakMilestone>("/admin/streaks/milestones", data).then((r) => r.data);

export const updateStreakMilestone = (id: number, data: Partial<StreakMilestone>) =>
  apiClient.patch<StreakMilestone>(`/admin/streaks/milestones/${id}`, data).then((r) => r.data);

export const deleteStreakMilestone = (id: number) =>
  apiClient.delete(`/admin/streaks/milestones/${id}`);

export const getUserStreaks = (skip = 0, limit = 50) =>
  apiClient.get<UserStreakRow[]>("/admin/streaks/users", { params: { skip, limit } }).then((r) => r.data);

export const resetUserStreak = (userId: number) =>
  apiClient.post(`/admin/streaks/users/${userId}/reset`).then((r) => r.data);

/* ── Streak Levels ─────────────────────────────────────── */

export interface StreakLevelRow {
  id: number;
  level: number;
  streak_days_required: number;
  bonus_credits: number;
  membership_plan_id: number | null;
  membership_duration_days: number;
  label: string;
  is_active: boolean;
}

export interface MembershipPlanOption {
  id: number;
  name: string;
  display_name: string;
  access_type: string;
  duration_days: number;
}

export const getStreakLevels = () =>
  apiClient.get<StreakLevelRow[]>("/admin/streaks/levels").then((r) => r.data);

export const createStreakLevel = (data: {
  level: number;
  streak_days_required: number;
  bonus_credits?: number;
  membership_plan_id?: number | null;
  membership_duration_days?: number;
  label?: string;
  is_active?: boolean;
}) =>
  apiClient.post<StreakLevelRow>("/admin/streaks/levels", data).then((r) => r.data);

export const updateStreakLevel = (id: number, data: Partial<StreakLevelRow>) =>
  apiClient.patch<StreakLevelRow>(`/admin/streaks/levels/${id}`, data).then((r) => r.data);

export const deleteStreakLevel = (id: number) =>
  apiClient.delete(`/admin/streaks/levels/${id}`);

export const getStreakMembershipPlans = () =>
  apiClient.get<MembershipPlanOption[]>("/admin/streaks/membership-plans").then((r) => r.data);

/* ── Dead Letter Queue ─────────────────────────────────── */

export interface DlqSummary {
  [queue: string]: number;
}

export interface DlqItem {
  original_queue: string;
  job: Record<string, unknown>;
  error: string;
  failed_at: number;
}

export interface DlqItemsResponse {
  queue: string;
  total: number;
  items: DlqItem[];
}

export const getDlqSummary = () =>
  apiClient.get<DlqSummary>("/admin/dlq/summary").then((r) => r.data);

export const getDlqItems = (queue: string, skip = 0, limit = 50) =>
  apiClient.get<DlqItemsResponse>("/admin/dlq/items", { params: { queue, skip, limit } }).then((r) => r.data);

export const retryDlqItems = (queue: string, count = 1) =>
  apiClient.post("/admin/dlq/retry", null, { params: { queue, count } }).then((r) => r.data);

export const purgeDlq = (queue: string) =>
  apiClient.delete("/admin/dlq/purge", { params: { queue } }).then((r) => r.data);

/* ── Content Factory ───────────────────────────────────── */

export const uploadVideo = (file: File, onProgress?: (pct: number, loaded?: number) => void, botId?: number, blur?: string, autoThumb?: boolean) => {
  const params = new URLSearchParams();
  if (botId) params.set("bot_id", String(botId));
  if (blur && blur !== "none") params.set("blur", blur);
  if (autoThumb === false) params.set("auto_thumb", "false");
  const qs = params.toString();
  // Dynamic timeout: 10 min base + 1 min per 10 MB (e.g. 500 MB → 60 min)
  const sizeMB = file.size / (1024 * 1024);
  const timeoutMs = Math.max(600_000, 600_000 + Math.ceil(sizeMB / 10) * 60_000);
  return apiClient
    .post(`/admin/content-factory/upload${qs ? `?${qs}` : ""}`, (() => { const fd = new FormData(); fd.append("file", file); return fd; })(), {
      headers: { "Content-Type": undefined },
      timeout: timeoutMs,
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total), e.loaded);
      },
    })
    .then((r) => r.data);
};

export const uploadThumbnail = (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return apiClient
    .post("/admin/content-factory/upload-thumbnail", fd, {
      headers: { "Content-Type": undefined },
      timeout: 60_000,
    })
    .then((r) => r.data);
};

export const extractFrame = (file: File, timestamp: number, blur?: string) => {
  const fd = new FormData();
  fd.append("file", file);
  const params = new URLSearchParams();
  params.set("timestamp", String(timestamp));
  if (blur && blur !== "none") params.set("blur", blur);
  const sizeMB = file.size / (1024 * 1024);
  const timeoutMs = Math.max(120_000, Math.ceil(sizeMB / 10) * 60_000);
  return apiClient
    .post(`/admin/content-factory/extract-frame?${params.toString()}`, fd, {
      headers: { "Content-Type": undefined },
      timeout: timeoutMs,
    })
    .then((r) => r.data as { file_id: string });
};

export const getFactoryCategories = () =>
  apiClient.get<ContentCategory[]>("/admin/content-factory/categories").then((r) => r.data);

export const getActiveBots = () =>
  apiClient.get<Bot[]>("/admin/bots/active").then((r) => r.data);

export const publishContent = (body: {
  mode: string;
  items: Array<{
    storage_chat_id: number;
    storage_message_id: number;
    media_type: string;
    title: string;
    access_type: string;
    credit_cost: number;
    credit_mode: string;
    credit_per_item: number;
    bot_id: number;
    thumbnail_file_id?: string | null;
  }>;
  group_settings?: {
    title: string;
    access_type: string;
    credit_cost: number;
    credit_mode: string;
    credit_per_item: number;
    bot_id: number;
    thumbnail_file_id?: string | null;
  } | null;
  rate_per_minute: number;
  deletion_seconds?: number | null;
}) => apiClient.post("/admin/content-factory/publish", body).then((r) => r.data);

export const getPublishJobs = () =>
  apiClient.get<PublishJob[]>("/admin/content-factory/jobs").then((r) => r.data);

export const getPublishJob = (jobId: string) =>
  apiClient.get<PublishJob>(`/admin/content-factory/jobs/${jobId}`).then((r) => r.data);

export const getFactoryContent = (skip = 0, limit = 50) =>
  apiClient.get<ContentItem[]>("/admin/content-factory/content", { params: { skip, limit } }).then((r) => r.data);

export const republishContent = (packId: number, botId: number, thumbnailFileId?: string | null) =>
  apiClient.post(`/admin/content-factory/republish/${packId}`, {
    bot_id: botId,
    thumbnail_file_id: thumbnailFileId || null,
  }).then((r) => r.data);

/* ── Default Thumbnails ────────────────────────────────── */

export const getDefaultThumbnails = () =>
  apiClient.get<Array<{ id: number; name: string; file_id: string }>>("/admin/content-factory/default-thumbnails").then((r) => r.data);

export const createDefaultThumbnail = (name: string, file_id: string) =>
  apiClient.post("/admin/content-factory/default-thumbnails", { name, file_id }).then((r) => r.data);

export const renameDefaultThumbnail = (id: number, name: string) =>
  apiClient.patch(`/admin/content-factory/default-thumbnails/${id}`, { name }).then((r) => r.data);

export const deleteDefaultThumbnail = (id: number) =>
  apiClient.delete(`/admin/content-factory/default-thumbnails/${id}`).then((r) => r.data);

export const deletePublishJob = (jobId: string) =>
  apiClient.delete(`/admin/content-factory/jobs/${jobId}`).then((r) => r.data);

/* ── Backups ───────────────────────────────────────────── */

export const getBackups = () =>
  apiClient.get("/admin/backups").then((r) => r.data);

export const triggerBackup = () =>
  apiClient.post("/admin/backups/trigger").then((r) => r.data);

export const downloadBackup = (filename: string) =>
  apiClient.get(`/admin/backups/${filename}/download`, { responseType: "blob" }).then((r) => r.data);

