/**
 * components/chat/CampusAssistantDrawer.tsx
 * -----------------------------------------
 * Shared compact, rounded floating AI Campus Assistant for RIO-MJP.
 * Uniformly mounted across ADMIN, FACULTY, and STUDENT portals.
 *
 * Full Feature Set:
 * - Persistent conversation sessions with history listing, switching, and deletion
 * - Grounded queries against authorized PostgreSQL records
 * - Role-tailored suggestion chips and empty-state guidance
 * - Structured timetable, room availability, booking, and announcement formatting
 * - Contextual quick navigation links to official RIO portal pages
 * - Resilient loading indicators and error recovery with retry
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Bot,
  Sparkles,
  Send,
  X,
  RotateCcw,
  Calendar,
  Building2,
  CheckCircle2,
  AlertCircle,
  Paperclip,
  MessageSquare,
  Plus,
  Trash2,
  ChevronDown,
  ArrowRight,
  RefreshCw,
  BookOpen,
  Briefcase,
} from 'lucide-react';
import { useAuth } from '@/auth/useAuth';
import {
  sendChatMessage,
  streamChatMessage,
  getConversations,
  getConversation,
  deleteConversation,
  type ChatHistoryMessage,
  type ConversationItem,
} from '@/api/chat';

let messageCounter = 0;
function nextMsgId(prefix: string): string {
  messageCounter += 1;
  return `${prefix}-${messageCounter}-${Date.now()}`;
}

export const CampusAssistantDrawer: React.FC = () => {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showAttachNotice, setShowAttachNotice] = useState(false);

  // Conversation session state
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [activeTitle, setActiveTitle] = useState<string>('New Conversation');
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [showConvDropdown, setShowConvDropdown] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRequestIdRef = useRef<string | null>(null);

  const [history, setHistory] = useState<ChatHistoryMessage[]>(() => [
    {
      id: 'welcome',
      sender: 'assistant',
      content: user
        ? `Hello **${user.name}**! I am **ATHENA**, your Knowledge-Driven Assistant. You can ask me any question about campus academics, schedules, departments, courses, rooms, or institutional operations.`
        : 'Hello! I am **ATHENA**, your Knowledge-Driven Assistant. How can I help you today?',
      timestamp: new Date(),
      sources: ['RIO Knowledge Engine'],
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load conversation list when assistant opens or user changes
  const loadConversations = useCallback(async () => {
    if (!user) return;
    try {
      const items = await getConversations(25);
      setConversations(items);
    } catch {
      // Non-blocking fallback
    }
  }, [user]);

  useEffect(() => {
    let ignore = false;
    if (isOpen && user) {
      getConversations(25)
        .then((items) => {
          if (!ignore) {
            setConversations(items);
          }
        })
        .catch(() => {
          // Non-blocking fallback
        });
    }
    return () => {
      ignore = true;
    };
  }, [isOpen, user]);

  // Sync conversation initial greeting when user session changes
  const [trackedUserId, setTrackedUserId] = useState<number | undefined>(user?.id);
  if (user && user.id !== trackedUserId) {
    setTrackedUserId(user.id);
    setActiveConversationId(null);
    setActiveTitle('New Conversation');
    setHistory([
      {
        id: nextMsgId('user_init'),
        sender: 'assistant',
        content: `Hello **${user.name}**! How can I assist you with your campus schedule or academic queries today?`,
        timestamp: new Date(),
        sources: ['RIO Knowledge Engine'],
      },
    ]);
  }

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      inputRef.current?.focus();
    }
  }, [history, isOpen]);

  useEffect(() => {
    if (!isLoading) return;
    const intervalId = window.setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isLoading]);

  if (!user) return null;

  const handleCancelStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
      setStreamingStatus(null);
    }
  };

  const handleSendMessage = async (msgText?: string) => {
    const textToSend = (msgText ?? inputMessage).trim();
    if (!textToSend || isLoading) return;

    const requestId = nextMsgId('req');
    activeRequestIdRef.current = requestId;

    const userMsg: ChatHistoryMessage = {
      id: nextMsgId('user'),
      sender: 'user',
      content: textToSend,
      timestamp: new Date(),
      conversation_id: activeConversationId ?? undefined,
    };

    const assistantMsgId = nextMsgId('assistant');

    setHistory((prev) => [...prev, userMsg]);
    setInputMessage('');
    setElapsedSeconds(0);
    setIsLoading(true);
    setStreamingStatus('Receiving your message...');

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let accumulatedText = '';
    let hasReceivedTokens = false;

    const upsertAssistantMessage = (patch: Partial<ChatHistoryMessage> & { content: string }) => {
      setHistory((prev) => {
        const exists = prev.some((m) => m.id === assistantMsgId);
        if (exists) {
          return prev.map((m) => (m.id === assistantMsgId ? { ...m, ...patch } : m));
        }
        return [
          ...prev,
          {
            id: assistantMsgId,
            sender: 'assistant',
            timestamp: new Date(),
            conversation_id: activeConversationId ?? undefined,
            ...patch,
          },
        ];
      });
    };

    try {
      await streamChatMessage(
        textToSend,
        activeConversationId ?? undefined,
        {
          onStatus: (st) => {
            if (activeRequestIdRef.current !== requestId || hasReceivedTokens) return;
            setStreamingStatus(st);
          },
          onToken: (tok) => {
            if (activeRequestIdRef.current !== requestId) return;
            if (!hasReceivedTokens) {
              hasReceivedTokens = true;
              setIsLoading(false);
              setStreamingStatus(null);
            }
            accumulatedText += tok;
            upsertAssistantMessage({ content: accumulatedText });
          },
          onDone: (data) => {
            if (activeRequestIdRef.current !== requestId) return;
            setIsLoading(false);
            setStreamingStatus(null);
            if (data.conversation_id && data.conversation_id !== activeConversationId) {
              setActiveConversationId(data.conversation_id);
              const snippet = textToSend.slice(0, 30) + (textToSend.length > 30 ? '...' : '');
              setActiveTitle(snippet);
              loadConversations();
            }
            upsertAssistantMessage({
              content: data.reply || accumulatedText || 'Query processed.',
              intent: data.intent,
              sources: data.sources,
              error: data.error,
              proposal: data.proposal,
              action_type: data.action_type,
              conversation_id: data.conversation_id,
              nav_links: data.nav_links,
              provider_badge: data.provider_badge,
              outcome_state: data.outcome_state,
            });
          },
          onError: (errMsg) => {
            if (activeRequestIdRef.current !== requestId) return;
            setIsLoading(false);
            setStreamingStatus(null);
            upsertAssistantMessage({
              content: accumulatedText ? accumulatedText + `\n\n[Error: ${errMsg}]` : `Error: ${errMsg}`,
              error: errMsg,
              provider_badge: 'System Notice',
            });
          },
        },
        controller.signal
      );
    } catch {
      if (activeRequestIdRef.current !== requestId) return;
      if (controller.signal.aborted) {
        upsertAssistantMessage({
          content: accumulatedText ? accumulatedText + ' (Cancelled by user)' : 'Request cancelled by user.',
          provider_badge: 'System Notice',
        });
      } else {
        // Fallback to synchronous sendChatMessage
        try {
          const res = await sendChatMessage(textToSend, activeConversationId ?? undefined);
          if (activeRequestIdRef.current !== requestId) return;
          upsertAssistantMessage({
            content: res.reply,
            intent: res.intent,
            sources: res.sources,
            error: res.error,
            proposal: res.proposal,
            action_type: res.action_type,
            conversation_id: res.conversation_id,
            nav_links: res.nav_links,
            provider_badge: res.provider_badge,
            outcome_state: res.outcome_state,
          });
        } catch (syncErr: unknown) {
          if (activeRequestIdRef.current !== requestId) return;
          const cleanErr = syncErr instanceof Error ? syncErr.message : String(syncErr);
          upsertAssistantMessage({
            content: `Error: ${cleanErr}`,
            error: cleanErr,
            provider_badge: 'System Notice',
          });
        }
      }
    } finally {
      if (activeRequestIdRef.current === requestId) {
        setIsLoading(false);
        setStreamingStatus(null);
        abortControllerRef.current = null;
        activeRequestIdRef.current = null;
      }
    }
  };

  const handleRetryLast = () => {
    // Find the last user message to resend
    const lastUserMsg = [...history].reverse().find((m) => m.sender === 'user');
    if (lastUserMsg) {
      handleSendMessage(lastUserMsg.content);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const startNewConversation = () => {
    setActiveConversationId(null);
    setActiveTitle('New Conversation');
    setShowConvDropdown(false);
    setHistory([
      {
        id: nextMsgId('new_chat'),
        sender: 'assistant',
        content: `New conversation started. How can I help you, **${user.name}**?`,
        timestamp: new Date(),
        sources: ['RIO Knowledge Engine'],
      },
    ]);
  };

  const switchConversation = async (conv: ConversationItem) => {
    try {
      setIsLoading(true);
      setShowConvDropdown(false);
      setActiveConversationId(conv.id);
      setActiveTitle(conv.title);

      const detail = await getConversation(conv.id);
      const restoredMsgs: ChatHistoryMessage[] = detail.messages.map((m) => ({
        id: `msg-${m.id}`,
        sender: m.sender,
        content: m.content,
        timestamp: new Date(m.created_at || Date.now()),
        intent: m.intent ?? undefined,
        sources: m.sources ?? undefined,
        conversation_id: m.conversation_id,
      }));

      if (restoredMsgs.length === 0) {
        restoredMsgs.push({
          id: nextMsgId('empty_conv'),
          sender: 'assistant',
          content: `Resumed conversation: **${conv.title}**. Ask a question to continue.`,
          timestamp: new Date(),
          sources: ['RIO Knowledge Engine'],
        });
      }

      setHistory(restoredMsgs);
    } catch {
      // Handle error gracefully
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteConversation = async (e: React.MouseEvent, convId: number) => {
    e.stopPropagation();
    try {
      await deleteConversation(convId);
      if (activeConversationId === convId) {
        startNewConversation();
      }
      loadConversations();
    } catch {
      // Handled silently
    }
  };

  // Icon resolver for backend-verified navigation links
  const getNavLinkIcon = (label: string, to: string) => {
    const s = (label + ' ' + to).toLowerCase();
    if (s.includes('timetable') || s.includes('schedule')) return <Calendar size={12} />;
    if (s.includes('resource') || s.includes('room') || s.includes('facility')) return <Building2 size={12} />;
    if (s.includes('course')) return <BookOpen size={12} />;
    if (s.includes('event') || s.includes('club')) return <Sparkles size={12} />;
    if (s.includes('placement') || s.includes('cdc')) return <Briefcase size={12} />;
    return <ArrowRight size={12} />;
  };

  // Render inline markdown (**bold**, *italic*, and `code`)
  const renderInlineMarkdown = (line: string, keyPrefix: string) => {
    const parts = line.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return (
          <strong key={`${keyPrefix}-b-${i}`} className="font-semibold text-slate-900">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith('*') && part.endsWith('*') && part.length > 2 && !part.startsWith('**')) {
        return (
          <em key={`${keyPrefix}-i-${i}`} className="italic text-slate-800">
            {part.slice(1, -1)}
          </em>
        );
      }
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
        return (
          <code
            key={`${keyPrefix}-c-${i}`}
            className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 font-mono text-[12px]"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      return <React.Fragment key={`${keyPrefix}-t-${i}`}>{part}</React.Fragment>;
    });
  };

  // Rich Markdown rendering supporting headings, paragraphs, bullet/numbered lists, blockquotes, code blocks, and tables
  const renderCleanContent = (text: string) => {
    const lines = text.split('\n');
    const blocks: React.ReactNode[] = [];
    let idx = 0;

    while (idx < lines.length) {
      const line = lines[idx];
      const trimmed = line.trim();

      // Fenced code blocks (```lang ... ```)
      if (trimmed.startsWith('```')) {
        const lang = trimmed.slice(3).trim();
        idx += 1;
        const codeLines: string[] = [];
        while (idx < lines.length && !lines[idx].trim().startsWith('```')) {
          codeLines.push(lines[idx]);
          idx += 1;
        }
        if (idx < lines.length && lines[idx].trim().startsWith('```')) {
          idx += 1;
        }
        blocks.push(
          <div key={`code-${idx}`} className="my-2 rounded-lg overflow-hidden border border-slate-200 bg-slate-900 text-slate-100">
            {lang && (
              <div className="px-3 py-1 text-[10px] font-mono uppercase tracking-wider text-slate-400 bg-slate-800 border-b border-slate-700">
                {lang}
              </div>
            )}
            <pre className="p-3 text-xs font-mono overflow-x-auto leading-relaxed">
              <code>{codeLines.join('\n')}</code>
            </pre>
          </div>
        );
        continue;
      }

      // Markdown headings (#, ##, ###, etc.)
      const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        const headingText = headingMatch[2];
        const headingClass =
          level === 1
            ? 'text-[15px] font-bold text-slate-900 mt-2.5 mb-1'
            : level === 2
              ? 'text-[14px] font-bold text-slate-900 mt-2 mb-1'
              : 'text-[13.5px] font-semibold text-slate-800 mt-1.5 mb-0.5';
        blocks.push(
          <div key={`h-${idx}`} className={headingClass}>
            {renderInlineMarkdown(headingText, `h-${idx}`)}
          </div>
        );
        idx += 1;
        continue;
      }

      // Blockquotes (> ...)
      if (trimmed.startsWith('>')) {
        const quoteLines: string[] = [];
        while (idx < lines.length && lines[idx].trim().startsWith('>')) {
          quoteLines.push(lines[idx].trim().replace(/^>\s?/, ''));
          idx += 1;
        }
        blocks.push(
          <blockquote
            key={`bq-${idx}`}
            className="border-l-3 border-blue-400 bg-blue-50/50 pl-3 py-1.5 my-1.5 text-slate-700 rounded-r-md space-y-1"
          >
            {quoteLines.map((ql, qIdx) => (
              <p key={qIdx} className="leading-relaxed">
                {renderInlineMarkdown(ql, `bq-${idx}-${qIdx}`)}
              </p>
            ))}
          </blockquote>
        );
        continue;
      }

      // Horizontal rule (--- or ***)
      if (/^(?:---+|\*\*\*+)$/.test(trimmed)) {
        blocks.push(<hr key={`hr-${idx}`} className="border-slate-200 my-2" />);
        idx += 1;
        continue;
      }

      // Detect valid Markdown table: header row + separator row (| --- | --- |)
      if (
        trimmed.startsWith('|') &&
        trimmed.endsWith('|') &&
        idx + 1 < lines.length &&
        /^\|[\s:|-]+\|$/.test(lines[idx + 1].trim())
      ) {
        const parseCells = (row: string) =>
          row
            .trim()
            .slice(1, -1)
            .split('|')
            .map((c) => c.trim());

        const headers = parseCells(trimmed);
        idx += 2; // skip header and separator
        const rows: string[][] = [];
        while (idx < lines.length && lines[idx].trim().startsWith('|') && lines[idx].trim().endsWith('|')) {
          rows.push(parseCells(lines[idx].trim()));
          idx += 1;
        }

        blocks.push(
          <div key={`tbl-${idx}`} className="overflow-x-auto my-2 rounded-lg border border-slate-200">
            <table className="min-w-full text-left text-xs border-collapse">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {headers.map((h, hIdx) => (
                    <th key={hIdx} className="px-2.5 py-1.5 font-semibold text-slate-700 whitespace-nowrap">
                      {renderInlineMarkdown(h, `th-${idx}-${hIdx}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r, rIdx) => (
                  <tr key={rIdx} className="hover:bg-slate-50/70">
                    {headers.map((_, cIdx) => (
                      <td key={cIdx} className="px-2.5 py-1.5 text-slate-700">
                        {renderInlineMarkdown(r[cIdx] ?? '', `td-${idx}-${rIdx}-${cIdx}`)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        continue;
      }

      // Bullet list items (- or * or •)
      if (/^\s*[-*•]\s+/.test(line)) {
        const listItems: string[] = [];
        while (idx < lines.length && /^\s*[-*•]\s+/.test(lines[idx])) {
          listItems.push(lines[idx].replace(/^\s*[-*•]\s+/, ''));
          idx += 1;
        }
        blocks.push(
          <ul key={`ul-${idx}`} className="list-disc pl-5 space-y-1 my-1.5">
            {listItems.map((item, liIdx) => (
              <li key={liIdx}>{renderInlineMarkdown(item, `li-${idx}-${liIdx}`)}</li>
            ))}
          </ul>
        );
        continue;
      }

      // Numbered list items (1. , 2. , etc.)
      if (/^\s*\d+\.\s+/.test(line)) {
        const numItems: string[] = [];
        while (idx < lines.length && /^\s*\d+\.\s+/.test(lines[idx])) {
          numItems.push(lines[idx].replace(/^\s*\d+\.\s+/, ''));
          idx += 1;
        }
        blocks.push(
          <ol key={`ol-${idx}`} className="list-decimal pl-5 space-y-1 my-1.5">
            {numItems.map((item, niIdx) => (
              <li key={niIdx}>{renderInlineMarkdown(item, `oli-${idx}-${niIdx}`)}</li>
            ))}
          </ol>
        );
        continue;
      }

      // Empty line -> spacing
      if (!trimmed) {
        idx += 1;
        continue;
      }

      // Regular paragraph line
      blocks.push(
        <p key={`p-${idx}`} className="leading-relaxed">
          {renderInlineMarkdown(line, `p-${idx}`)}
        </p>
      );
      idx += 1;
    }

    return <div className="space-y-2">{blocks}</div>;
  };

  const isErrorMessage = (msg: ChatHistoryMessage) => {
    return Boolean(
      msg.error ||
      msg.content.toLowerCase().startsWith('error:') ||
      msg.content.startsWith('⚠️')
    );
  };

  return (
    <>
      {/* ── Floating Launcher Button (when closed) ──────────────────────────── */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-blue-500/25 cursor-pointer"
          title="Open ATHENA — Knowledge-Driven Assistant"
          aria-label="Open ATHENA"
        >
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-300 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
          </span>
          <Sparkles size={17} className="text-blue-100" />
          <span className="font-semibold text-sm tracking-wide">Ask ATHENA</span>
        </button>
      )}

      {/* ── Compact Floating Panel with Dimmed Background ────────────────────── */}
      {isOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/20 backdrop-blur-[2px] transition-all flex justify-end items-end sm:items-center p-0 sm:p-4 md:p-6 lg:p-8">
          {/* Backdrop click to dismiss */}
          <div
            className="fixed inset-0"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />

          {/* Floating Chat Container */}
          <div
            className="relative z-10 w-full sm:w-[540px] md:w-[600px] h-[92vh] sm:h-[calc(100vh-64px)] max-h-[850px] bg-white rounded-t-[28px] sm:rounded-[28px] shadow-2xl border border-slate-200/90 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
            role="dialog"
            aria-modal="true"
            aria-label="ATHENA — Knowledge-Driven Assistant"
          >
            {/* Header */}
            <div className="px-5 sm:px-6 py-4 bg-white border-b border-slate-100 flex items-center justify-between shrink-0 gap-2">
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="w-11 h-11 rounded-2xl bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                  <Bot size={22} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <h3 className="font-bold text-[17px] text-slate-900 leading-tight tracking-tight truncate">
                      ATHENA
                    </h3>
                    <span className="px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider rounded-full bg-blue-100 text-blue-700 shrink-0">
                      Role: {user.role}
                    </span>
                  </div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-blue-600 leading-tight truncate mt-0.5">
                    KNOWLEDGE-DRIVEN ASSISTANT
                  </p>
                  {/* Active Conversation Picker */}
                  <div className="relative mt-0.5">
                    <button
                      type="button"
                      onClick={() => setShowConvDropdown((prev) => !prev)}
                      className="inline-flex items-center gap-1.5 text-xs text-slate-600 font-medium hover:text-blue-600 truncate max-w-[240px] cursor-pointer"
                      title="Switch conversation"
                    >
                      <MessageSquare size={12} className="shrink-0 text-slate-400" />
                      <span className="truncate">{activeTitle}</span>
                      <ChevronDown size={12} className="shrink-0 text-slate-400" />
                    </button>

                    {/* Conversations Dropdown */}
                    {showConvDropdown && (
                      <div className="absolute left-0 top-6 z-30 w-72 max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-xl p-2 animate-in fade-in slide-in-from-top-2 duration-150">
                        <div className="flex items-center justify-between pb-2 mb-1 border-b border-slate-100 px-2">
                          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                            Saved Sessions
                          </span>
                          <button
                            type="button"
                            onClick={startNewConversation}
                            className="inline-flex items-center gap-1 text-xs text-blue-600 font-semibold hover:text-blue-700 cursor-pointer"
                          >
                            <Plus size={13} />
                            <span>New</span>
                          </button>
                        </div>
                        {conversations.length === 0 ? (
                          <div className="p-3 text-xs text-slate-400 text-center">
                            No prior conversations yet.
                          </div>
                        ) : (
                          <div className="space-y-1">
                            {conversations.map((c) => (
                              <div
                                key={c.id}
                                onClick={() => switchConversation(c)}
                                className={`flex items-center justify-between px-2.5 py-2 text-xs rounded-lg cursor-pointer transition-colors ${
                                  c.id === activeConversationId
                                    ? 'bg-blue-50 text-blue-700 font-semibold'
                                    : 'text-slate-700 hover:bg-slate-50'
                                }`}
                              >
                                <span className="truncate flex-1 pr-2">{c.title}</span>
                                <button
                                  type="button"
                                  onClick={(e) => handleDeleteConversation(e, c.id)}
                                  className="text-slate-400 hover:text-rose-600 p-1 rounded-md transition-colors shrink-0"
                                  title="Delete conversation"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={startNewConversation}
                  className="w-9 h-9 rounded-full border border-slate-200 hover:border-slate-300 text-slate-600 hover:text-slate-900 hover:bg-slate-50 flex items-center justify-center transition-colors shadow-2xs cursor-pointer"
                  title="Start New Conversation"
                  aria-label="New conversation"
                >
                  <RotateCcw size={15} />
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="w-9 h-9 rounded-full border border-slate-200 hover:border-slate-300 text-slate-600 hover:text-slate-900 hover:bg-slate-50 flex items-center justify-center transition-colors shadow-2xs cursor-pointer"
                  title="Close Assistant"
                  aria-label="Close assistant"
                >
                  <X size={17} />
                </button>
              </div>
            </div>

            {/* Scrollable Message History */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 bg-[#F8FAFC]">
              {history.map((msg) => {
                const isUser = msg.sender === 'user';
                const isErr = isErrorMessage(msg);
                const timeStr = msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const navLinks = !isUser && msg.nav_links && msg.nav_links.length > 0 ? msg.nav_links : [];

                if (isUser) {
                  return (
                    <div key={msg.id} className="flex items-start justify-end gap-2.5">
                      <div className="flex flex-col items-end max-w-[82%]">
                        <div className="bg-blue-600 text-white font-medium text-[13.5px] leading-relaxed px-4 py-2.5 rounded-2xl shadow-2xs">
                          {msg.content}
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-slate-400 mt-1 pr-1 font-medium">
                          <span>{timeStr}</span>
                        </div>
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={msg.id} className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-xl bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-2xs mt-0.5">
                      <Bot size={18} />
                    </div>

                    <div className="flex flex-col items-start max-w-[85%]">
                      <div
                        className={`text-[13.5px] leading-relaxed px-4 py-3 rounded-2xl shadow-2xs space-y-3 w-full ${
                          isErr
                            ? 'bg-rose-50 border border-rose-200 text-rose-900'
                            : 'bg-white border border-slate-200/90 text-slate-800'
                        }`}
                      >
                        {isErr && (
                          <div className="flex items-center gap-1.5 font-bold text-xs text-rose-700">
                            <AlertCircle size={15} />
                            <span>System Notice</span>
                          </div>
                        )}

                        <div className="whitespace-pre-wrap font-normal text-slate-800">
                          {renderCleanContent(msg.content)}
                        </div>

                        {/* Verified Backend Navigation Links */}
                        {navLinks.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 flex items-center gap-2 flex-wrap">
                            {navLinks.map((lnk, lIdx) => (
                              <Link
                                key={lIdx}
                                to={lnk.to}
                                onClick={() => setIsOpen(false)}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 hover:text-blue-800 border border-blue-200 transition-colors"
                              >
                                {getNavLinkIcon(lnk.label, lnk.to)}
                                <span>{lnk.label}</span>
                                <ArrowRight size={11} />
                              </Link>
                            ))}
                          </div>
                        )}

                        {/* Interactive Proposal Card */}
                        {msg.proposal && (
                          <div className="p-3.5 bg-blue-50/80 border border-blue-200 rounded-xl space-y-2.5 text-xs text-slate-800">
                            <div className="flex items-center justify-between font-bold text-blue-900 border-b border-blue-200/60 pb-2">
                              <span className="flex items-center gap-1.5">
                                <Sparkles size={14} className="text-blue-600" />
                                <span>{msg.proposal.resource_id ? 'Resource Booking Proposal' : 'Timetable Action Proposal'}</span>
                              </span>
                              <span className="font-mono text-[10px] text-blue-600 bg-white px-2 py-0.5 rounded-full border border-blue-200">
                                {msg.proposal.proposal_id}
                              </span>
                            </div>

                            {msg.proposal.resource_id ? (
                              <div className="space-y-1.5 text-slate-700">
                                <p><strong className="text-slate-900">Facility:</strong> {msg.proposal.resource_name} ({msg.proposal.resource_type})</p>
                                <p><strong className="text-slate-900">Interval:</strong> {msg.proposal.date} {msg.proposal.start_time} - {msg.proposal.end_time}</p>
                                <p><strong className="text-slate-900">Purpose:</strong> {msg.proposal.purpose || 'Standard booking'}</p>
                              </div>
                            ) : (
                              <div className="space-y-1 text-slate-700">
                                <p><strong className="text-slate-900">Scope:</strong> {msg.proposal.scope_display?.department} (Sem {msg.proposal.scope_display?.semester})</p>
                                <p><strong className="text-slate-900">Strategy:</strong> {msg.proposal.strategy || 'BALANCED'}</p>
                              </div>
                            )}

                            <div className="flex items-center gap-2 pt-1">
                              <button
                                type="button"
                                onClick={() => handleSendMessage(`confirm ${msg.proposal?.proposal_id}`)}
                                disabled={isLoading}
                                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                              >
                                <CheckCircle2 size={13} />
                                <span>Authorize Action</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSendMessage('cancel that')}
                                disabled={isLoading}
                                className="py-1.5 px-3 bg-slate-200 hover:bg-slate-300 text-slate-700 font-medium text-xs rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                              >
                                <span>Dismiss</span>
                              </button>
                            </div>
                          </div>
                        )}

                        {isErr && (
                          <div className="pt-2 border-t border-rose-100 flex items-center gap-3">
                            <button
                              type="button"
                              onClick={handleRetryLast}
                              className="inline-flex items-center gap-1 text-xs font-semibold text-rose-700 hover:text-rose-900 bg-rose-100/60 hover:bg-rose-100 px-2.5 py-1 rounded-md transition-colors cursor-pointer"
                            >
                              <RotateCcw size={11} />
                              <span>Retry</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSendMessage('help')}
                              className="inline-flex items-center gap-1 text-xs font-semibold text-rose-700 hover:text-rose-900 underline cursor-pointer"
                            >
                              <RefreshCw size={11} />
                              <span>Show available operations</span>
                            </button>
                          </div>
                        )}
                      </div>

                      <span className="text-[11px] text-slate-400 mt-1 pl-1">
                        {timeStr}
                      </span>
                    </div>
                  </div>
                );
              })}

              {isLoading && (
                <div
                  className="flex items-start gap-3"
                  role="status"
                  aria-live="polite"
                  aria-label="ATHENA is thinking"
                >
                  <div className="w-8 h-8 rounded-xl bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-2xs mt-0.5">
                    <Bot size={18} />
                  </div>
                  <div className="bg-white border border-blue-200/80 rounded-2xl px-4 py-3 shadow-2xs flex-1 max-w-[85%] flex flex-col gap-1.5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2.5 text-[13px] font-medium text-slate-700 min-w-0">
                        <span className="flex gap-1 shrink-0" aria-hidden="true">
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                        </span>
                        <span className="truncate">
                          {streamingStatus || 'Connecting to ATHENA...'}
                          {elapsedSeconds > 0 ? ` · ${elapsedSeconds}s` : ''}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={handleCancelStreaming}
                        className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1 border border-slate-200 transition-colors cursor-pointer shrink-0"
                        title="Cancel streaming request"
                        aria-label="Cancel request"
                      >
                        <X size={12} />
                        <span>Cancel</span>
                      </button>
                    </div>
                    {elapsedSeconds >= 15 && (
                      <p className="text-[11.5px] text-slate-500 pl-6">
                        Still waiting for the response. This is taking longer than usual...
                      </p>
                    )}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input Bar */}
            <div className="p-4 bg-white border-t border-slate-100 shrink-0">
              <div className="bg-white border border-slate-200/90 rounded-full pl-3.5 pr-1.5 py-1.5 flex items-center gap-2 shadow-2xs focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
                <button
                  type="button"
                  onClick={() => setShowAttachNotice((prev) => !prev)}
                  className="p-1.5 text-slate-400 hover:text-slate-600 rounded-full transition-colors shrink-0 focus:outline-none cursor-pointer"
                  title="Campus database connectivity active"
                  aria-label="Database connectivity"
                >
                  <Paperclip size={18} />
                </button>
                <input
                  ref={inputRef}
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isLoading}
                  placeholder="Ask ATHENA anything about campus operations, schedules, academics, or records..."
                  className="flex-1 min-w-0 text-[13.5px] text-slate-800 placeholder-slate-400 bg-transparent border-0 border-none outline-none ring-0 shadow-none focus:outline-none focus:ring-0 focus:border-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0"
                  style={{
                    border: 'none',
                    outline: 'none',
                    boxShadow: 'none',
                    background: 'transparent',
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleSendMessage()}
                  disabled={!inputMessage.trim() || isLoading}
                  className="w-9 h-9 rounded-full bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center shadow-sm shrink-0 transition-all active:scale-95 cursor-pointer focus:outline-none"
                  title="Send Message"
                  aria-label="Send message"
                >
                  <Send size={15} className="translate-x-[-0.5px]" />
                </button>
              </div>

              {showAttachNotice && (
                <div className="mt-2 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-2 flex items-center justify-between">
                  <span>Assistant is connected to live PostgreSQL records. All facts are authoritative and grounded.</span>
                  <button
                    onClick={() => setShowAttachNotice(false)}
                    className="text-slate-400 hover:text-slate-700 font-bold ml-2 text-xs cursor-pointer"
                  >
                    ✕
                  </button>
                </div>
              )}
            </div>

          </div>
        </div>
      )}
    </>
  );
};
