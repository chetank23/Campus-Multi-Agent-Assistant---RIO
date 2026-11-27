/**
 * frontend/src/api/chat.ts
 * ------------------------
 * Client interface for the RIO-MJP Multi-Agent Campus Assistant.
 * Provides conversation persistence, history listing, session creation, and message exchange.
 */

import { apiClient, getAccessToken, getApiBaseUrl, setAccessToken } from './client';

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
 * Includes automatic 401 token refresh, CRLF/LF frame parsing, EOF buffer flush,
 * and guaranteed terminal-event handling.
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
  const baseUrl = getApiBaseUrl();

  const doStreamFetch = (accessToken: string | null) =>
    fetch(`${baseUrl}/agents/chat/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({
        message: message.trim(),
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
      signal,
    });

  let response = await doStreamFetch(getAccessToken());

  // Attempt silent token refresh once on 401 Unauthorized
  if (response.status === 401 && !signal?.aborted) {
    try {
      const refreshResp = await fetch(`${baseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal,
      });
      if (refreshResp.ok) {
        const refreshData = await refreshResp.json();
        const newToken = refreshData?.access_token as string | undefined;
        if (newToken) {
          setAccessToken(newToken);
          response = await doStreamFetch(newToken);
        }
      }
    } catch {
      // Fall through to error handling below
    }
  }

  if (!response.ok) {
    let errDetail = response.status === 401
      ? 'Your session has expired. Please sign in again.'
      : 'Failed to stream message';
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
  let receivedTerminalEvent = false;

  const processFrame = (frame: string) => {
    const trimmed = frame.trim();
    if (!trimmed || trimmed.startsWith(':')) return;
    // Handle multi-line SSE data frames cleanly
    const dataLines = trimmed
      .split(/\r?\n/)
      .filter((l) => l.startsWith('data:'))
      .map((l) => l.slice(5).trim());
    if (dataLines.length === 0) return;
    const dataStr = dataLines.join('\n');
    try {
      const payload: StreamEventData = JSON.parse(dataStr);
      if (payload.event === 'status' && payload.status) {
        callbacks.onStatus?.(payload.status);
      } else if (payload.event === 'token' && payload.token) {
        callbacks.onToken?.(payload.token);
      } else if (payload.event === 'done') {
        receivedTerminalEvent = true;
        callbacks.onDone?.(payload);
      } else if (payload.event === 'error') {
        receivedTerminalEvent = true;
        callbacks.onError?.(payload.error || 'Stream error occurred');
      }
    } catch {
      // Skip unparseable block
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      if (buffer.trim()) {
        for (const rem of buffer.split(/\r?\n\r?\n/)) {
          processFrame(rem);
        }
      }
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || '';
    for (const frame of frames) {
      processFrame(frame);
    }
  }

  if (!receivedTerminalEvent && !signal?.aborted) {
    callbacks.onError?.('The assistant stream closed unexpectedly before completing. Please try again.');
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
