/* ── Domain types (match backend Pydantic schemas) ────────── */

export interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  level: number;
  created_at: string;
  last_active_at: string | null;
  blocked_until: string | null;
}

export interface Bot {
  id: number;
  bot_username: string;
  status: string;
  cleanup_hours?: number;
  created_at: string;
  last_used_at: string | null;
  user_count?: number;
}

export interface ContentPack {
  id: number;
  title: string;
  description: string | null;
  access_type: string;
  credit_cost: number;
  credit_mode: string;        // per_pack | per_item
  credit_per_item: number;
  deletion_seconds: number | null;
  created_at: string;
}

export interface PackItem {
  id: number;
  pack_id: number;
  storage_chat_id: number;
  storage_message_id: number;
  media_type: string;
  order_index: number;
}

export interface Token {
  token: string;
  pack_id: number;
  single_use: boolean;
  used_count: number;
  bound_user_id: number | null;
  expires_at: string | null;
  created_at: string;
}

export interface Credit {
  user_id: number;
  balance: number;
}

export interface CreditHistory {
  id: number;
  user_id: number;
  change_amount: number;
  reason: string;
  created_at: string;
}

export interface Membership {
  id: number;
  user_id: number;
  membership_type: string;
  start_at: string;
  expiry_at: string | null;
}

export interface Payment {
  id: number;
  user_id: number;
  amount: number;
  method: string;
  reference: string;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export interface Referral {
  id: number;
  invite_code: string;
  referrer_user_id: number;
  used_by_user_id: number | null;
  reward_granted: boolean;
  created_at: string;
}

export interface ActivityLog {
  id: number;
  user_id: number;
  action: string;
  payload: string | null;
  created_at: string;
}

export interface DashboardSummary {
  total_users: number;
  total_bots: number;
  total_packs: number;
  total_deliveries: number;
  total_payments: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

/* ── Payment System types ──────────────────────────────── */

export interface MembershipPlan {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  access_type: string;
  price_inr: number;
  credit_price: number;
  duration_days: number;
  duration_hours: number;
  credit_reward: number;
  is_active: boolean;
  sort_order: number;
  tier_level: number;
  active_member_count: number;
  created_at: string;
}

export interface PlanMember {
  membership_id: number;
  user_id: number;
  telegram_id: number;
  username: string | null;
  membership_type: string;
  start_at: string;
  expiry_at: string | null;
}

export interface UpiConfig {
  id: number;
  upi_id: string;
  payee_name: string;
  is_active: boolean;
  created_at: string;
}

export interface SmsLog {
  id: number;
  sender: string;
  body: string;
  received_at: string;
  utr_extracted: string | null;
  amount_extracted: number | null;
  matched: boolean;
  matched_order_id: number | null;
  created_at: string;
}

export interface PaymentOrder {
  id: number;
  user_id: number;
  plan_id: number;
  amount: number;
  upi_id_used: string;
  order_ref: string;
  status: string;
  utr_submitted: string | null;
  verified_at: string | null;
  expires_at: string;
  created_at: string;
}

export interface PaymentStats {
  total_orders: number;
  pending: number;
  utr_submitted: number;
  verified: number;
  failed: number;
  expired: number;
  total_revenue: number;
}

/* ── Platform Settings ─────────────────────────────────── */

export interface PlatformSetting {
  id: number;
  key: string;
  value: string;
  description: string | null;
  category: string;
  created_at: string | null;
  updated_at: string | null;
}

/* ── Content Factory ───────────────────────────────────── */

export interface UploadedVideo {
  id: string;
  filename: string;
  file: File | null;  // kept until upload completes
  storage_chat_id: number;
  storage_message_id: number;
  file_id: string;
  media_type: string;
  duration?: number;
  width?: number;
  height?: number;
  title: string;
  access_type: string;
  credit_cost: number;
  credit_mode: string;
  credit_per_item: number;
  bot_id: number;
  thumbnail_file_id?: string;
  uploading: boolean;
  uploaded: boolean;  // true once upload to TG succeeded
  error?: string;
}

export interface ContentCategory {
  tag: string;
  label: string;
}

export interface PublishJob {
  id: string;
  status: string;
  mode: string;
  total: number;
  completed: number;
  failed: number;
  results: PublishResult[];
  error?: string;
  rate_per_minute: number;
  created_at?: string;
}

export interface PublishResult {
  pack_id?: number;
  token?: string;
  deep_link?: string;
  items_count?: number;
  channel_posted?: boolean;
  title?: string;
  error?: string;
  index?: number;
}

export interface ContentItem {
  id: number;
  title: string;
  description: string | null;
  access_type: string;
  credit_cost: number;
  credit_mode: string;
  credit_per_item: number;
  deletion_seconds: number | null;
  created_at: string;
  item_count: number;
  token: string | null;
  deep_link: string | null;
  views: number;
}

export interface DefaultThumbnail {
  id: number;
  name: string;
  file_id: string;
}