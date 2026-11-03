export type DigitalHumanStatus = "idle" | "listening" | "thinking" | "speaking";

export interface DigitalHumanConversationSummary {
  id: string;
  skill_code: "digital_human";
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface DigitalHumanConversationListResponse {
  items: DigitalHumanConversationSummary[];
  limit: number;
  offset: number;
  total_count: number;
}

export interface TranscriptionResponse {
  text: string;
}
