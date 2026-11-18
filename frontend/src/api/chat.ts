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
  user_query?: string;
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

export interface StreamStatusData {
  status: string;
  message: string;
}

export interface StreamToolData {
  tool: string;
  records_count?: number;
}

export interface StreamCallbacks {
  onToken?: (token: string) => void;
  onStatus?: (status: StreamStatusData) => void;
  onToolStart?: (data: StreamToolData) => void;
  onToolDone?: (data: StreamToolData) => void;
  onDone?: (res: ChatMessageResponse) => void;
  onError?: (err: string) => void;
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
 * Streams real-time model tokens, tool execution phases, and completion events via SSE.
 */
export async function streamChatMessage(
  message: string,
  conversationId: number | undefined,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const baseUrl = getApiBaseUrl();
  const token = getAccessToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${baseUrl}/agents/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message: message.trim(),
      conversation_id: conversationId,
    }),
    signal,
  });

  if (!response.ok) {
    const errText = await response.text();
    let errDetail = errText;
    try {
      const errJson = JSON.parse(errText);
      errDetail = errJson.detail || errText;
    } catch {
      // raw string
    }
    throw new Error(errDetail || `Server returned status ${response.status}`);
  }

  if (!response.body) {
    throw new Error('Streaming response body is unavailable.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');

        if (!frame) continue;

        let eventType = 'message';
        let dataStr = '';

        const lines = frame.split('\n');
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            dataStr = line.slice(5).trim();
          }
        }

        if (!dataStr) continue;

        try {
          const parsedData = JSON.parse(dataStr);
          if (eventType === 'status') {
            callbacks.onStatus?.(parsedData);
          } else if (eventType === 'tool_start') {
            callbacks.onToolStart?.(parsedData);
          } else if (eventType === 'tool_done') {
            callbacks.onToolDone?.(parsedData);
          } else if (eventType === 'token') {
            callbacks.onToken?.(parsedData.token || '');
          } else if (eventType === 'done') {
            callbacks.onDone?.(parsedData as ChatMessageResponse);
          } else if (eventType === 'error') {
            callbacks.onError?.(parsedData.error || 'Streaming error occurred.');
          }
        } catch {
          // ignore malformed frame
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
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
