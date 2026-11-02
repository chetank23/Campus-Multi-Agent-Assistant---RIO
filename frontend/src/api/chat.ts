/**
 * frontend/src/api/chat.ts
 * ------------------------
 * Client interface for the RIO-MJP Multi-Agent Campus Assistant.
 * Provides conversation persistence, history listing, session creation, and message exchange.
 */

import { apiClient } from './client';

export interface ChatMessageRequest {
  message: string;
  conversation_id?: number;
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

  // Resource Booking Proposal Fields
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
  conversation_id?: number;
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
  conversation_id?: number;
}

export interface ConversationItem {
  id: number;
  title: string;
  role: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatMessageDetail {
  id: number;
  conversation_id: number;
  sender: 'user' | 'assistant';
  content: string;
  intent?: string | null;
  tool_calls?: ChatToolCall[] | null;
  sources?: string[] | null;
  created_at: string;
}

export interface ConversationDetail {
  id: number;
  title: string;
  role: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessageDetail[];
}

/**
 * Sends a message to the authenticated AI Agent Supervisor endpoint.
 */
export async function sendChatMessage(
  message: string,
  conversationId?: number
): Promise<ChatMessageResponse> {
  const payload: ChatMessageRequest = {
    message: message.trim(),
  };
  if (conversationId) {
    payload.conversation_id = conversationId;
  }
  const response = await apiClient.post<ChatMessageResponse>('/agents/chat', payload);
  return response.data;
}

/**
 * Lists the authenticated user's chat conversations.
 */
export async function getConversations(limit: number = 20): Promise<ConversationItem[]> {
  const response = await apiClient.get<ConversationItem[]>('/agents/conversations', {
    params: { limit },
  });
  return response.data;
}

/**
 * Creates a new conversation session.
 */
export async function createConversation(title?: string): Promise<ConversationItem> {
  const response = await apiClient.post<ConversationItem>('/agents/conversations', {
    title: title || 'New Conversation',
  });
  return response.data;
}

/**
 * Retrieves full message history for a specific conversation.
 */
export async function getConversation(conversationId: number): Promise<ConversationDetail> {
  const response = await apiClient.get<ConversationDetail>(`/agents/conversations/${conversationId}`);
  return response.data;
}

/**
 * Deletes a conversation session and all its messages.
 */
export async function deleteConversation(conversationId: number): Promise<void> {
  await apiClient.delete(`/agents/conversations/${conversationId}`);
}
