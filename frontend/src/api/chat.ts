/**
 * frontend/src/api/chat.ts
 * ------------------------
 * Client interface for the RIO-MJP Multi-Agent Campus Assistant.
 * Provides conversation persistence, history listing, session creation, and message exchange.
 */

import { apiClient, getAccessToken, getApiBaseUrl } from './client';

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

export interface NavLinkItem {
  label: string;
  to: string;
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
  diagnostics?: Record<string, unknown>;
  nav_links?: NavLinkItem[];
  provider_badge?: string;
  outcome_state?: string;
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
  nav_links?: NavLinkItem[];
  provider_badge?: string;
  outcome_state?: string;
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

export interface StreamEventData {
  event: 'token' | 'status' | 'done' | 'error';
  token?: string;
  status?: string;
  reply?: string;
  error?: string;
  nav_links?: NavLinkItem[];
  provider_badge?: string;
  outcome_state?: string;
  conversation_id?: number;
  intent?: string;
  sources?: string[];
  tool_calls?: ChatToolCall[];
  proposal?: ChatProposalData | null;
  action_type?: string | null;
  success?: boolean;
}

/**
 * Sends a message and streams SSE token chunks and events from the backend.
 */
export async function streamChatMessage(
  message: string,
  conversationId: number | undefined,
  callbacks: {
    onStatus?: (status: string) => void;
    onToken?: (token: string) => void;
    onDone?: (data: StreamEventData) => void;
    onError?: (error: string) => void;
  },
  signal?: AbortSignal
): Promise<void> {
  const token = getAccessToken();
  const baseUrl = getApiBaseUrl();
  const response = await fetch(`${baseUrl}/agents/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message: message.trim(),
      ...(conversationId ? { conversation_id: conversationId } : {}),
    }),
    signal,
  });

  if (!response.ok) {
    let errDetail = 'Failed to stream message';
    try {
      const errJson = await response.json();
      errDetail = errJson.detail || errDetail;
    } catch {
      // fallback
    }
    callbacks.onError?.(errDetail);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.('Streaming response body is unavailable');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const block of lines) {
      const trimmed = block.trim();
      if (!trimmed.startsWith('data:')) continue;
      const dataStr = trimmed.slice(5).trim();
      try {
        const payload: StreamEventData = JSON.parse(dataStr);
        if (payload.event === 'status' && payload.status) {
          callbacks.onStatus?.(payload.status);
        } else if (payload.event === 'token' && payload.token) {
          callbacks.onToken?.(payload.token);
        } else if (payload.event === 'done') {
          callbacks.onDone?.(payload);
        } else if (payload.event === 'error') {
          callbacks.onError?.(payload.error || 'Stream error occurred');
        }
      } catch {
        // Skip unparseable block
      }
    }
  }
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
