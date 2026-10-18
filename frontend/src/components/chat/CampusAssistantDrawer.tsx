/**
 * components/chat/CampusAssistantDrawer.tsx
 * -----------------------------------------
 * Slide-over drawer and floating launcher for the RIO-MJP Multi-Agent Campus Assistant.
 * Fully integrated across Admin, Faculty, and Student portals.
 * Answers are strictly grounded in verified campus databases.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Bot,
  Sparkles,
  Send,
  X,
  RotateCcw,
  Clock,
  Calendar,
  Building2,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Play,
  Settings2,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { sendChatMessage, type ChatHistoryMessage } from '@/api/chat';

let messageCounter = 0;
function nextMsgId(prefix: string): string {
  messageCounter += 1;
  return `${prefix}-${messageCounter}`;
}

export const CampusAssistantDrawer: React.FC = () => {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<ChatHistoryMessage[]>(() => [
    {
      id: 'welcome',
      sender: 'assistant',
      content: 'Hello! I am your **RIO Campus Assistant**.\n\nI can answer questions grounded in the official university database, such as your **published class timetable**, **next class status**, **course syllabus details**, **room locations**, or **academic holidays**.' +
        (user?.role === 'ADMIN' ? '\n\nAs an **Admin**, I can also resolve academic scopes, inspect data readiness, explain optimization strategies, and prepare validated timetable generation proposals.' : ''),
      timestamp: new Date(),
      sources: ['Verified Campus Database'],
    },
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
      const errorMsg: ChatHistoryMessage = {
        id: nextMsgId('err'),
        sender: 'assistant',
        content: `⚠️ **Service Temporarily Unavailable**: ${errorDetail}`,
        timestamp: new Date(),
        error: errorDetail,
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

  // Role-specific quick prompt recommendations
  const getSuggestions = () => {
    if (user.role === 'STUDENT') {
      return [
        { label: 'Find seminar halls', icon: <Building2 size={13} /> },
        { label: 'Show my bookings', icon: <Clock size={13} /> },
        { label: 'What is my next class?', icon: <Clock size={13} /> },
        { label: 'Where is Room 101?', icon: <Building2 size={13} /> },
      ];
    } else if (user.role === 'FACULTY') {
      return [
        { label: 'Find seminar halls', icon: <Building2 size={13} /> },
        { label: 'Show my bookings', icon: <Clock size={13} /> },
        { label: 'My teaching schedule today', icon: <Calendar size={13} /> },
        { label: 'Upcoming university events', icon: <Calendar size={13} /> },
      ];
    } else {
      return [
        { label: 'Generate timetable for CSE Semester 1', icon: <Play size={13} /> },
        { label: 'Find seminar halls', icon: <Building2 size={13} /> },
        { label: 'Compare scheduling strategies', icon: <Settings2 size={13} /> },
        { label: 'Show my bookings', icon: <Clock size={13} /> },
      ];
    }
  };

  return (
    <>
      {/* ── Floating Launcher Button ─────────────────────────────────────────── */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2.5 px-4 py-3 bg-gradient-to-r from-blue-700 via-indigo-700 to-primary-700 hover:from-blue-800 hover:to-primary-800 text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-primary-500/30"
        title="Open RIO Campus AI Assistant"
        aria-label="Open Campus AI Assistant"
      >
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-400"></span>
        </span>
        <Sparkles size={18} className="text-cyan-300" />
        <span className="font-semibold text-sm tracking-wide">Ask RIO AI</span>
      </button>

      {/* ── Slide-Over Assistant Drawer ──────────────────────────────────────── */}
      {isOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/30 backdrop-blur-[2px] transition-opacity">
          <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-screen max-w-md sm:max-w-lg bg-white shadow-2xl flex flex-col border-l border-slate-200">
              
              {/* Header */}
              <div className="px-5 py-4 bg-[#142542] text-white flex items-center justify-between border-b border-slate-700">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white shadow-sm">
                    <Bot size={20} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-base text-white leading-tight">
                        RIO Campus Assistant
                      </h3>
                      <span className="px-1.5 py-0.5 text-[10px] uppercase font-bold tracking-wider rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                        Agent 9A
                      </span>
                    </div>
                    <p className="text-xs text-slate-300">
                      Grounded database engine &bull; {user.role} Portal
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={clearChat}
                    className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                    title="Clear Conversation"
                    aria-label="Clear chat"
                  >
                    <RotateCcw size={16} />
                  </button>
                  <button
                    onClick={() => setIsOpen(false)}
                    className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
                    title="Close Assistant"
                    aria-label="Close drawer"
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* Suggestions chips */}
              <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200/80 overflow-x-auto no-scrollbar flex items-center gap-2">
                <span className="text-[11px] font-semibold text-slate-400 whitespace-nowrap uppercase tracking-wider">
                  Suggestions:
                </span>
                {getSuggestions().map((s, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(s.label)}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-white hover:bg-primary-50 text-slate-700 hover:text-primary-700 border border-slate-200 hover:border-primary-300 whitespace-nowrap transition-all shadow-2xs"
                  >
                    {s.icon}
                    <span>{s.label}</span>
                  </button>
                ))}
              </div>

              {/* Chat Message Scroll Area */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#F8FAFC]">
                {history.map((msg) => {
                  const isUser = msg.sender === 'user';
                  return (
                    <div
                      key={msg.id}
                      className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                    >
                      <div
                        className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-xs ${
                          isUser
                            ? 'bg-gradient-to-r from-blue-700 to-indigo-700 text-white rounded-tr-xs'
                            : 'bg-white text-slate-800 border border-slate-200/80 rounded-tl-xs'
                        }`}
                      >
                        {/* Message content rendering */}
                        <div className="whitespace-pre-wrap break-words prose prose-slate prose-sm max-w-none">
                          {msg.content}
                        </div>

                        {/* Proposal Interactive Card */}
                        {!isUser && msg.proposal && (
                          <div className="mt-3 p-3.5 rounded-xl bg-slate-50 border border-slate-200/90 shadow-2xs space-y-2.5">
                            {msg.proposal.proposal_id.startsWith('res_prop_') ? (
                              <>
                                <div className="flex items-center justify-between">
                                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                                    <Building2 size={13} className="text-primary-600" />
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
                                    <span className="font-medium text-indigo-700 font-mono text-[11px]">
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
                                  className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-medium text-xs rounded-lg shadow-xs hover:shadow-md transition-all duration-150 disabled:opacity-50"
                                >
                                  <CheckCircle2 size={14} />
                                  <span>Confirm &amp; Submit Booking</span>
                                </button>
                              </>
                            ) : (
                              <>
                                <div className="flex items-center justify-between">
                                  <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                                    <Settings2 size={13} className="text-primary-600" />
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
                                    <span className="font-medium text-indigo-700 font-mono text-[11px]">
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
                                    className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-medium text-xs rounded-lg shadow-xs hover:shadow-md transition-all duration-150 disabled:opacity-50"
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

                        {/* Source citations for assistant responses */}
                        {!isUser && msg.sources && msg.sources.length > 0 && (
                          <div className="mt-2.5 pt-2 border-t border-slate-100 flex flex-wrap items-center gap-1.5">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                              Source:
                            </span>
                            {msg.sources.map((src, sIdx) => (
                              <span
                                key={sIdx}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-50 text-emerald-700 border border-emerald-200/60"
                              >
                                <ShieldCheck size={10} />
                                {src}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      <span className="text-[10px] text-slate-400 px-1 mt-1">
                        {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  );
                })}

                {isLoading && (
                  <div className="flex items-start gap-2.5">
                    <div className="w-7 h-7 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center shrink-0 mt-0.5">
                      <Bot size={15} />
                    </div>
                    <div className="bg-white border border-slate-200/80 rounded-2xl rounded-tl-xs px-4 py-3 shadow-xs">
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

              {/* Input Area */}
              <div className="p-3 bg-white border-t border-slate-200">
                <div className="flex items-center gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isLoading}
                    placeholder="Ask about your timetable, classes, faculty, or campus..."
                    className="flex-1 px-3.5 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-600 transition-all text-slate-800 placeholder-slate-400"
                  />
                  <button
                    onClick={() => handleSendMessage()}
                    disabled={!inputMessage.trim() || isLoading}
                    className="p-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl shadow-xs transition-colors shrink-0"
                    title="Send Message"
                    aria-label="Send message"
                  >
                    <Send size={16} />
                  </button>
                </div>
                <p className="text-[10px] text-center text-slate-400 mt-2">
                  Answers are generated by RIO Query Agent using PostgreSQL as the single source of truth.
                </p>
              </div>

            </div>
          </div>
        </div>
      )}
    </>
  );
};
