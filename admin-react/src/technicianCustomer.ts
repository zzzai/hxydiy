export type Page<T> = { items: T[]; total: number; page: number; page_size: number };
export type TechnicianCustomerTask = {
  occupancy_id: number; user_id: number | null; selection_session_id: string;
  occupancy_status: 'in_service' | 'post_service_present';
  room_id: number; room_name: string; items: { name?: string; quantity?: number; project_id?: number; code?: string; diy_preferences?: unknown }[];
  pricing?: {
    store_total_cents?: number | null;
    member_total_cents?: number | null;
    applied_price_type?: 'store' | 'member' | 'group' | null;
    lines?: {
      line_index?: number;
      name?: string;
      quantity?: number;
      unit_store_price_cents?: number | null;
      unit_member_price_cents?: number | null;
      store_line_total_cents?: number | null;
      member_line_total_cents?: number | null;
    }[];
  } | null;
};
export type CustomerSummary = {
  occupancy_id: number; customer_id: number | null; customer_name: string | null;
  access: 'granted' | 'unbound'; membership: { level: string | null } | null;
};
export type CustomerHistoryItem = {
  id: number; selection_session_id: string; service_started_at: string | null; service_finished_at: string | null;
  projects: { name: string; quantity: number }[];
};
export type CustomerReviewItem = {
  id: number; rating: number | null; content: string; created_at: string;
  feedback_type: 'service' | 'visit'; source: string; tags: string[]; projects: { name: string; quantity: number }[];
};
export type CustomerReportItem = { id: string; created_at: string | null; title: string };
export type CustomerReportDetail = CustomerReportItem & { sections: { title: string; content: string }[] };
export type TagOption = { id: number; name: string; color: string | null };
export type CustomerOperationalTag = TagOption & {
  sources: { kind: 'legacy' | 'contribution'; contribution_id: number | null; owned_by_me: boolean; version: number | null }[];
};
export type CustomerTags = { items: CustomerOperationalTag[]; available_tags: TagOption[] };
