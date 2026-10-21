/**
 * components/chat/CampusAssistantDrawer.tsx
 * -----------------------------------------
 * Shared compact, rounded floating AI Chat Assistant for RIO-MJP.
 * Uniformly mounted across ADMIN, FACULTY, and STUDENT portals.
 *
 * Visual design matches visual reference:
 * - Floating rounded panel (~590px wide on desktop) on the right of the viewport
 * - Large rounded corners (rounded-[28px]), soft shadow, subtle cool-grey border
 * - Dimmed, slightly blurred background with underlying dashboard visible
 * - Clean white card header with blue robot avatar, Agent badge, portal context, and reset/close controls
 * - Role-aware horizontal suggestion chips
 * - Left-aligned assistant messages in white cards with robot avatar and green source badges
 * - Right-aligned user messages in blue bubbles with user avatar and double-check timestamps
 * - Red alert styling for error states
 * - Interactive proposal cards for facility bookings and timetable generation
 * - Fixed bottom input bar with rounded pill field, attachment icon, and blue send button
 */

import React, { useState, useRef, useEffect } from 'react';
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
  Play,
  Settings2,
  Database,
  HelpCircle,
  Paperclip,
  User,
  CheckCheck,
  Clock,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { sendChatMessage, type ChatHistoryMessage } from '@/api/chat';

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

  const [history, setHistory] = useState<ChatHistoryMessage[]>(() => [
    {
      id: 'welcome',
      sender: 'assistant',
      content: user ? `Conversation reset. How can I help you today, **${user.name}**?` : 'Conversation reset. How can I help you today?',
      timestamp: new Date(),
      sources: ['RIO Knowledge Engine'],
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync conversation initial greeting when user session changes
  const [trackedUserId, setTrackedUserId] = useState<number | undefined>(user?.id);
  if (user && user.id !== trackedUserId) {
    setTrackedUserId(user.id);
    setHistory([
      {
        id: nextMsgId('user_init'),
        sender: 'assistant',
        content: `Conversation reset. How can I help you today, **${user.name}**?`,
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
    };

    setHistory((prev) => [...prev, userMsg]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const res = await sendChatMessage(textToSend);
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
      };
      setHistory((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorDetail =
        err.response?.data?.detail || err.message || 'Unable to connect to the Assistant service.';
      const cleanError = typeof errorDetail === 'object'
        ? (errorDetail.message || JSON.stringify(errorDetail))
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

  const clearChat = () => {
    setHistory([
      {
        id: nextMsgId('cleared'),
        sender: 'assistant',
        content: `Conversation reset. How can I help you today, **${user.name}**?`,
        timestamp: new Date(),
        sources: ['RIO Knowledge Engine'],
      },
    ]);
  };

  // Role-specific suggestions based on authenticated role and supported capabilities
  const getSuggestions = (): { label: string; prompt: string; icon: React.ReactNode }[] => {
    if (user.role === 'STUDENT') {
      return [
        { label: 'What is my next class?', prompt: 'What is my next class?', icon: <HelpCircle size={13} /> },
        { label: 'View my timetable', prompt: 'View my timetable', icon: <Calendar size={13} /> },
        { label: 'How many classrooms are there?', prompt: 'How many classrooms are there?', icon: <Building2 size={13} /> },
        { label: 'Show my bookings', prompt: 'Show my bookings', icon: <Clock size={13} /> },
      ];
    } else if (user.role === 'FACULTY') {
      return [
        { label: 'View my timetable', prompt: 'View my timetable', icon: <Calendar size={13} /> },
        { label: 'What is my next class?', prompt: 'What is my next class?', icon: <HelpCircle size={13} /> },
        { label: 'Find a seminar hall', prompt: 'Find a seminar hall', icon: <Building2 size={13} /> },
        { label: 'Show my bookings', prompt: 'Show my bookings', icon: <Clock size={13} /> },
      ];
    } else if (user.role === 'ADMIN') {
      return [
        { label: 'Generate timetable', prompt: 'Generate timetable for CSE Semester 1', icon: <Play size={13} /> },
        { label: 'Check timetable readiness', prompt: 'Check timetable readiness for CSE Semester 1', icon: <CheckCircle2 size={13} /> },
        { label: 'View pending resource bookings', prompt: 'View pending resource bookings', icon: <Clock size={13} /> },
        { label: 'Check resource availability', prompt: 'Check resource availability', icon: <Building2 size={13} /> },
        { label: 'Compare scheduling strategies', prompt: 'Compare scheduling strategies', icon: <Settings2 size={13} /> },
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

  // Safe formatting without raw markdown asterisks or headings
  const renderCleanContent = (text: string) => {
    // Strip decorative leading hashes (#, ##, ###)
    let clean = text.replace(/^\s*#{1,6}\s+/gm, '');
    // Replace markdown bullets (* ) with bullet character
    clean = clean.replace(/^\s*\*\s+/gm, '• ');

    // Parse **bold** into <strong>
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
            className="relative z-10 w-full sm:w-[540px] md:w-[590px] h-[92vh] sm:h-[calc(100vh-64px)] max-h-[840px] bg-white rounded-t-[28px] sm:rounded-[28px] shadow-2xl border border-slate-200/90 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
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
                      Agent 9A
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 font-medium mt-0.5 truncate">
                    Grounded database engine &bull; {user.role} Portal
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={clearChat}
                  className="w-9 h-9 rounded-full border border-slate-200 hover:border-slate-300 text-slate-600 hover:text-slate-900 hover:bg-slate-50 flex items-center justify-center transition-colors shadow-2xs"
                  title="Reset Conversation"
                  aria-label="Reset conversation"
                >
                  <RotateCcw size={15} />
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="w-9 h-9 rounded-full border border-slate-200 hover:border-slate-300 text-slate-600 hover:text-slate-900 hover:bg-slate-50 flex items-center justify-center transition-colors shadow-2xs"
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
                Suggestions:
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

                if (isUser) {
                  return (
                    <div key={msg.id} className="flex items-start justify-end gap-2.5">
                      <div className="flex flex-col items-end max-w-[80%]">
                        <div className="bg-blue-600 text-white font-medium text-[13.5px] leading-relaxed px-4 py-2.5 rounded-2xl shadow-2xs">
                          {msg.content}
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-slate-400 mt-1 pr-1 font-medium">
                          <span>{timeStr}</span>
                          <CheckCheck size={14} className="text-blue-500" />
                        </div>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0 mt-0.5 shadow-2xs">
                        <User size={16} />
                      </div>
                    </div>
                  );
                }

                if (isErr) {
                  return (
                    <div key={msg.id} className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-full bg-rose-500 text-white flex items-center justify-center shrink-0 shadow-2xs mt-0.5">
                        <AlertCircle size={18} />
                      </div>
                      <div className="flex flex-col max-w-[85%]">
                        <div className="bg-rose-50 border border-rose-200/90 text-rose-900 font-medium px-4 py-3 rounded-2xl text-[13.5px] shadow-2xs">
                          {msg.content.replace(/^⚠️\s*/, '')}
                        </div>
                        <span className="text-[11px] text-slate-400 mt-1 pl-1">
                          {timeStr}
                        </span>
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={msg.id} className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 shadow-2xs mt-0.5">
                      <Bot size={18} />
                    </div>
                    <div className="flex flex-col max-w-[85%]">
                      <div className="bg-white border border-slate-200/90 rounded-2xl p-4 text-[13.5px] leading-relaxed text-slate-800 shadow-2xs space-y-3">
                        <div className="whitespace-pre-wrap break-words">
                          {renderCleanContent(msg.content)}
                        </div>

                        {/* Proposal Interactive Card */}
                        {msg.proposal && (
                          <div className="mt-3 p-3.5 rounded-xl bg-slate-50 border border-slate-200/90 shadow-2xs space-y-2.5">
                            {msg.proposal.proposal_id.startsWith('res_prop_') ? (
                              <>
                                <div className="flex items-center justify-between">
                                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                                    <Building2 size={13} className="text-blue-600" />
                                    Facility Booking Proposal
                                  </span>
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
                                    Verified Available
                                  </span>
                                </div>

                                <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 bg-white p-2.5 rounded-lg border border-slate-100">
                                  <div>
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Facility</span>
                                    <span className="font-medium text-slate-800">
                                      {msg.proposal.resource_name} ({msg.proposal.resource_type})
                                    </span>
                                  </div>
                                  <div>
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Date</span>
                                    <span className="font-medium text-slate-800 font-mono text-[11px]">
                                      {msg.proposal.date}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Time Interval</span>
                                    <span className="font-medium text-blue-700 font-mono text-[11px]">
                                      {msg.proposal.start_time?.slice(0, 5)} &ndash; {msg.proposal.end_time?.slice(0, 5)}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Location</span>
                                    <span className="font-medium text-slate-800">
                                      {msg.proposal.location || 'Main Campus'}
                                    </span>
                                  </div>
                                  {msg.proposal.purpose && (
                                    <div className="col-span-2">
                                      <span className="font-semibold text-slate-500 block text-[10px] uppercase">Purpose</span>
                                      <span className="font-medium text-slate-700">
                                        {msg.proposal.purpose}
                                      </span>
                                    </div>
                                  )}
                                </div>

                                <button
                                  onClick={() => handleSendMessage(`confirm ${msg.proposal?.proposal_id}`)}
                                  disabled={isLoading}
                                  className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs rounded-lg shadow-2xs hover:shadow-sm transition-all duration-150 disabled:opacity-50"
                                >
                                  <CheckCircle2 size={14} />
                                  <span>Confirm &amp; Submit Booking</span>
                                </button>
                              </>
                            ) : (
                              <>
                                <div className="flex items-center justify-between">
                                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                                    <Settings2 size={13} className="text-blue-600" />
                                    Timetable Proposal
                                  </span>
                                  <span
                                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                      msg.proposal.readiness_status === 'READY'
                                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                                        : msg.proposal.readiness_status === 'READY_WITH_WARNINGS'
                                        ? 'bg-amber-100 text-amber-800 border border-amber-300'
                                        : 'bg-rose-100 text-rose-800 border border-rose-300'
                                    }`}
                                  >
                                    {msg.proposal.readiness_status}
                                  </span>
                                </div>

                                <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 bg-white p-2.5 rounded-lg border border-slate-100">
                                  <div>
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Scope</span>
                                    <span className="font-medium text-slate-800">
                                      {msg.proposal.scope_display?.department || 'Department'} &bull; {msg.proposal.scope_display?.semester || 'Semester'}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Strategy</span>
                                    <span className="font-medium text-blue-700 font-mono text-[11px]">
                                      {msg.proposal.strategy}
                                    </span>
                                  </div>
                                  <div className="col-span-2">
                                    <span className="font-semibold text-slate-500 block text-[10px] uppercase">Academic Year</span>
                                    <span className="font-medium text-slate-800">
                                      {msg.proposal.scope_display?.academic_year || 'Current'}
                                    </span>
                                  </div>
                                </div>

                                {msg.proposal.readiness_status !== 'BLOCKED' ? (
                                  <button
                                    onClick={() => handleSendMessage(`confirm ${msg.proposal?.proposal_id}`)}
                                    disabled={isLoading}
                                    className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs rounded-lg shadow-2xs hover:shadow-sm transition-all duration-150 disabled:opacity-50"
                                  >
                                    <CheckCircle2 size={14} />
                                    <span>Authorize &amp; Generate Timetable</span>
                                  </button>
                                ) : (
                                  <div className="flex items-center gap-1.5 p-2 bg-rose-50 text-rose-700 text-xs rounded-lg border border-rose-200">
                                    <AlertTriangle size={14} className="shrink-0" />
                                    <span>Generation is blocked until data issues are resolved.</span>
                                  </div>
                                )}
                              </>
                            )}
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
                  className="p-1.5 text-slate-400 hover:text-slate-600 rounded-full transition-colors shrink-0 focus:outline-none"
                  title="Attach reference"
                  aria-label="Attach file"
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
                  placeholder="Ask about your timetable, classes, faculty, or campus..."
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
                  <span>Query Agent accesses verified university database records directly. File attachments are optional.</span>
                  <button
                    onClick={() => setShowAttachNotice(false)}
                    className="text-slate-400 hover:text-slate-700 font-bold ml-2 text-xs"
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
