/**
 * frontend/src/api/chat.ts
 * ------------------------
 * Client interface for the RIO-MJP Multi-Agent Campus Assistant.
 */

import { apiClient } from './client';

export interface ChatMessageRequest {
  message: string;
}

export interface ChatToolCall {
  tool: string;
  args: Record<string, unknown>;
}

export interface ChatProposalData {
  proposal_id: string;
  scope_display?: {
    department?: string;
    program?: string;
    semester?: string;
    academic_year?: string;
    sections_count?: string;
    section_names?: string;
  };
  strategy?: string;
  readiness_status?: string;
  revision?: number;
  superseded?: boolean;
  superseded_by?: string | null;
  expires_at?: number;

  // Stage 9C: Resource Booking Proposal Fields
  resource_id?: number;
  resource_name?: string;
  resource_type?: string;
  location?: string | null;
  capacity?: number | null;
  date?: string;
  start_time?: string;
  end_time?: string;
  purpose?: string;

  // Real-Time AI Operations Capability Fields
  action_name?: string;
  target_entity_type?: string;
  target_entity_id?: string | number;
  parameters?: Record<string, unknown>;
  consequences?: string;
}

export interface ChatMessageResponse {
  reply: string;
  intent?: string;
  selected_agent?: string;
  tool_calls: ChatToolCall[];
  sources: string[];
  proposal?: ChatProposalData | null;
  action_type?: string | null;
  success: boolean;
  error?: string | null;
}

export interface ChatHistoryMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  intent?: string;
  sources?: string[];
  proposal?: ChatProposalData | null;
  action_type?: string | null;
  error?: string | null;
}


/**
 * Sends a message to the authenticated AI Agent Supervisor endpoint.
 */
export async function sendChatMessage(message: string): Promise<ChatMessageResponse> {
  const response = await apiClient.post<ChatMessageResponse>('/agents/chat', {
    message: message.trim(),
  });
  return response.data;
}
