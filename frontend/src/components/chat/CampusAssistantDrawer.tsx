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
  AlertTriangle,
  AlertCircle,
  Database,
  HelpCircle,
  Paperclip,
  Clock,
  MessageSquare,
  Plus,
  Trash2,
  ChevronDown,
  ArrowRight,
  RefreshCw,
  Bell,
  BookOpen,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import {
  sendChatMessage,
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

  const [history, setHistory] = useState<ChatHistoryMessage[]>(() => [
    {
      id: 'welcome',
      sender: 'assistant',
      content: user ? `Hello **${user.name}**! How can I assist you with your campus schedule or academic queries today?` : 'How can I assist you today?',
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
    if (isOpen && user) {
      loadConversations();
    }
  }, [isOpen, user, loadConversations]);

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

  if (!user) return null;

  const handleSendMessage = async (msgText?: string) => {
    const textToSend = (msgText ?? inputMessage).trim();
    if (!textToSend || isLoading) return;

    const userMsg: ChatHistoryMessage = {
      id: nextMsgId('user'),
      sender: 'user',
      content: textToSend,
      timestamp: new Date(),
      conversation_id: activeConversationId ?? undefined,
    };

    setHistory((prev) => [...prev, userMsg]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const res = await sendChatMessage(textToSend, activeConversationId ?? undefined);

      if (res.conversation_id && res.conversation_id !== activeConversationId) {
        setActiveConversationId(res.conversation_id);
        const snippet = textToSend.slice(0, 30) + (textToSend.length > 30 ? '...' : '');
        setActiveTitle(snippet);
        loadConversations();
      }

      const assistantMsg: ChatHistoryMessage = {
        id: nextMsgId('assistant'),
        sender: 'assistant',
        content: res.reply,
        timestamp: new Date(),
        intent: res.intent,
        sources: res.sources,
        error: res.error,
        proposal: res.proposal,
        action_type: res.action_type,
        conversation_id: res.conversation_id,
      };
      setHistory((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: unknown } }; message?: string };
      const errorDetail = errorObj.response?.data?.detail || errorObj.message || 'Unable to connect to the Assistant service.';
      const cleanError = typeof errorDetail === 'object'
        ? JSON.stringify(errorDetail)
        : String(errorDetail);

      const errorMsg: ChatHistoryMessage = {
        id: nextMsgId('err'),
        sender: 'assistant',
        content: `Error: ${cleanError}`,
        timestamp: new Date(),
        error: cleanError,
      };
      setHistory((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
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

  // Role-specific suggestions based on authenticated role and supported capabilities
  const getSuggestions = (): { label: string; prompt: string; icon: React.ReactNode }[] => {
    if (user.role === 'STUDENT') {
      return [
        { label: 'What is my timetable today?', prompt: 'What is my timetable today?', icon: <Calendar size={13} /> },
        { label: 'What classes do I have tomorrow?', prompt: 'What classes do I have tomorrow?', icon: <Clock size={13} /> },
        { label: 'Where is my next class?', prompt: 'Where is my next class?', icon: <HelpCircle size={13} /> },
        { label: 'Has my timetable changed?', prompt: 'Has my timetable changed?', icon: <AlertCircle size={13} /> },
        { label: 'Campus announcements', prompt: 'Are there any relevant campus announcements?', icon: <Bell size={13} /> },
        { label: 'My booking status', prompt: 'What is the status of my resource booking?', icon: <Clock size={13} /> },
      ];
    } else if (user.role === 'FACULTY') {
      return [
        { label: 'My teaching schedule today', prompt: 'What is my teaching schedule today?', icon: <Calendar size={13} /> },
        { label: 'Classes tomorrow', prompt: 'Which classes do I have tomorrow?', icon: <Clock size={13} /> },
        { label: 'Which rooms are assigned to me?', prompt: 'Which rooms are assigned to me?', icon: <Building2 size={13} /> },
        { label: 'Find free labs', prompt: 'Which available labs match a requested time slot?', icon: <Building2 size={13} /> },
        { label: 'My bookings status', prompt: 'What is the status of my own resource booking?', icon: <Clock size={13} /> },
      ];
    } else if (user.role === 'ADMIN') {
      return [
        { label: 'Department timetable', prompt: 'Show today timetable for department', icon: <Calendar size={13} /> },
        { label: 'Find available rooms', prompt: 'Find available rooms for a time slot', icon: <Building2 size={13} /> },
        { label: 'Timetable publication status', prompt: 'Check timetable publication status', icon: <CheckCircle2 size={13} /> },
        { label: 'Review pending bookings', prompt: 'Review pending resource bookings', icon: <Clock size={13} /> },
        { label: 'Timetable disruptions', prompt: 'Summarize recent timetable disruptions', icon: <AlertTriangle size={13} /> },
      ];
    } else {
      return [
        { label: 'Find a seminar hall', prompt: 'Find a seminar hall', icon: <Building2 size={13} /> },
        { label: 'Show my bookings', prompt: 'Show my bookings', icon: <Clock size={13} /> },
      ];
    }
  };

  // Source icon resolver
  const getSourceIcon = (src: string) => {
    const s = src.toLowerCase();
    if (s.includes('facilities') || s.includes('register') || s.includes('room')) {
      return <Building2 size={11} className="text-emerald-700 shrink-0" />;
    }
    return <Database size={11} className="text-emerald-700 shrink-0" />;
  };

  // Quick action links based on content context and role
  const getContextualLinks = (text: string) => {
    const t = text.toLowerCase();
    const links: { label: string; to: string; icon: React.ReactNode }[] = [];

    if (t.includes('timetable') || t.includes('schedule') || t.includes('class')) {
      if (user.role === 'STUDENT') {
        links.push({ label: 'Open Student Timetable', to: '/student/timetable', icon: <Calendar size={12} /> });
      } else if (user.role === 'FACULTY') {
        links.push({ label: 'Open Faculty Timetable', to: '/faculty/timetable', icon: <Calendar size={12} /> });
      } else if (user.role === 'ADMIN') {
        links.push({ label: 'Open Timetable Engine', to: '/admin/timetable', icon: <Calendar size={12} /> });
      }
    }

    if (t.includes('booking') || t.includes('facility') || t.includes('room') || t.includes('lab')) {
      if (user.role === 'FACULTY') {
        links.push({ label: 'Campus Resources', to: '/faculty/resources', icon: <Building2 size={12} /> });
      } else if (user.role === 'ADMIN') {
        links.push({ label: 'Manage Resources', to: '/admin/resources', icon: <Building2 size={12} /> });
      }
    }

    if (t.includes('course') && user.role === 'STUDENT') {
      links.push({ label: 'My Enrolled Courses', to: '/student/courses', icon: <BookOpen size={12} /> });
    }

    return links;
  };

  // Safe formatting without raw markdown asterisks or headings
  const renderCleanContent = (text: string) => {
    let clean = text.replace(/^\s*#{1,6}\s+/gm, '');
    clean = clean.replace(/^\s*\*\s+/gm, '• ');

    const parts = clean.split(/(\*\*[^*]+\*\*)/g);
    return (
      <>
        {parts.map((part, i) => {
          if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
            return (
              <strong key={i} className="font-semibold text-slate-900">
                {part.slice(2, -2)}
              </strong>
            );
          }
          return <span key={i}>{part}</span>;
        })}
      </>
    );
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
          title="Open RIO Campus AI Assistant"
          aria-label="Open Campus AI Assistant"
        >
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-300 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
          </span>
          <Sparkles size={17} className="text-blue-100" />
          <span className="font-semibold text-sm tracking-wide">Ask RIO AI</span>
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
            aria-label="RIO Campus Assistant"
          >
            {/* Header */}
            <div className="px-6 py-4 bg-white border-b border-slate-100 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="w-11 h-11 rounded-2xl bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                  <Bot size={22} />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-[17px] text-slate-900 leading-tight truncate">
                      RIO Campus Assistant
                    </h3>
                    <span className="px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider rounded-full bg-blue-100 text-blue-700 shrink-0">
                      Role: {user.role}
                    </span>
                  </div>
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

            {/* Suggestions Chips Row */}
            <div className="px-5 py-2.5 bg-white border-b border-slate-100 flex items-center gap-2 overflow-x-auto no-scrollbar shrink-0">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider shrink-0 mr-1">
                Suggested:
              </span>
              <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-0.5">
                {getSuggestions().map((s, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSendMessage(s.prompt)}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-white hover:bg-slate-50 text-slate-700 hover:text-blue-700 border border-slate-200 hover:border-blue-300 whitespace-nowrap transition-all shadow-2xs shrink-0 active:scale-95 disabled:opacity-50 cursor-pointer"
                  >
                    <span className="text-slate-500">{s.icon}</span>
                    <span>{s.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Scrollable Message History */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 bg-[#F8FAFC]">
              {history.map((msg) => {
                const isUser = msg.sender === 'user';
                const isErr = isErrorMessage(msg);
                const timeStr = msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const contextLinks = !isUser ? getContextualLinks(msg.content) : [];

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

                        {/* Contextual Deep-Links */}
                        {contextLinks.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 flex items-center gap-2 flex-wrap">
                            {contextLinks.map((lnk, lIdx) => (
                              <Link
                                key={lIdx}
                                to={lnk.to}
                                onClick={() => setIsOpen(false)}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 hover:text-blue-800 border border-blue-200 transition-colors"
                              >
                                {lnk.icon}
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

                        {/* Source Badges */}
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                              SOURCE:
                            </span>
                            {msg.sources.map((src, sIdx) => (
                              <span
                                key={sIdx}
                                className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-medium rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 shadow-2xs"
                              >
                                {getSourceIcon(src)}
                                <span>{src}</span>
                              </span>
                            ))}
                          </div>
                        )}

                        {isErr && (
                          <div className="pt-1">
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
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 shadow-2xs mt-0.5">
                    <Bot size={18} />
                  </div>
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-2xs">
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
                      <span className="flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                      </span>
                      <span>Consulting verified campus records&hellip;</span>
                    </div>
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
                  placeholder={`Ask RIO as ${user.role} (e.g. classes today, room availability, announcements)...`}
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
