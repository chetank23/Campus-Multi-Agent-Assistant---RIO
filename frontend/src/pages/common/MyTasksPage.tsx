/**
 * frontend/src/pages/common/MyTasksPage.tsx
 * -----------------------------------------
 * Personal To-Do List & Notepad for authenticated Students and Faculty.
 * Strictly private per authenticated user, persisted in PostgreSQL.
 */

import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CheckSquare,
  Plus,
  Pencil,
  Trash2,
  Calendar,
  Flag,
  CheckCircle2,
  Circle,
  Search,
  StickyNote,
} from 'lucide-react';
import { PageHeader, FormModal, LoadingState, EmptyState } from '@/components/common';
import {
  personalTasksApi,
  type PersonalTask,
  type TaskPriority,
  type TaskSortBy,
} from '@/api/personalTasks';
import { formatDateTime12h } from '@/utils/timeFormatter';

const PRIORITY_BADGE: Record<TaskPriority, { label: string; cls: string }> = {
  HIGH: { label: 'High', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  MEDIUM: { label: 'Medium', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  LOW: { label: 'Low', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
};

export const MyTasksPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [searchTerm, setSearchTerm] = useState('');
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | 'ALL'>('ALL');
  const [sortBy, setSortBy] = useState<TaskSortBy>('created_at');

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<PersonalTask | null>(null);
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [dueTime, setDueTime] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('MEDIUM');
  const [formError, setFormError] = useState<string | null>(null);

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['my-tasks', sortBy],
    queryFn: () => personalTasksApi.list({ sort_by: sortBy }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['my-tasks'] });

  const createMut = useMutation({
    mutationFn: personalTasksApi.create,
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err: unknown) => {
      setFormError(err instanceof Error ? err.message : 'Failed to create task.');
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Parameters<typeof personalTasksApi.update>[1] }) =>
      personalTasksApi.update(id, payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err: unknown) => {
      setFormError(err instanceof Error ? err.message : 'Failed to update task.');
    },
  });

  const toggleMut = useMutation({
    mutationFn: (id: number) => personalTasksApi.toggle(id),
    onSuccess: invalidate,
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => personalTasksApi.remove(id),
    onSuccess: invalidate,
  });

  const openCreateModal = () => {
    setEditingTask(null);
    setTitle('');
    setNotes('');
    setDueDate('');
    setDueTime('');
    setPriority('MEDIUM');
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (task: PersonalTask) => {
    setEditingTask(task);
    setTitle(task.title);
    setNotes(task.notes || '');
    if (task.due_at) {
      const iso = task.due_at.slice(0, 16);
      const [d, t] = iso.split('T');
      setDueDate(d || '');
      setDueTime(t || '');
    } else {
      setDueDate('');
      setDueTime('');
    }
    setPriority(task.priority);
    setFormError(null);
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingTask(null);
    setFormError(null);
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      setFormError('Please enter a task title.');
      return;
    }

    let dueAtIso: string | null = null;
    if (dueDate) {
      dueAtIso = `${dueDate}T${dueTime || '09:00'}:00`;
    }

    if (editingTask) {
      updateMut.mutate({
        id: editingTask.id,
        payload: {
          title: cleanTitle,
          notes: notes.trim(),
          due_at: dueAtIso,
          clear_due_at: !dueDate,
          priority,
        },
      });
    } else {
      createMut.mutate({
        title: cleanTitle,
        notes: notes.trim() || undefined,
        due_at: dueAtIso,
        priority,
      });
    }
  };

  const filteredTasks = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    return tasks.filter((t) => {
      if (priorityFilter !== 'ALL' && t.priority !== priorityFilter) return false;
      if (q && !t.title.toLowerCase().includes(q) && !(t.notes || '').toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [tasks, searchTerm, priorityFilter]);

  const pendingTasks = useMemo(
    () => filteredTasks.filter((t) => t.status === 'PENDING'),
    [filteredTasks]
  );
  const completedTasks = useMemo(
    () => filteredTasks.filter((t) => t.status === 'COMPLETED'),
    [filteredTasks]
  );

  const renderTaskCard = (task: PersonalTask) => {
    const isDone = task.status === 'COMPLETED';
    const prio = PRIORITY_BADGE[task.priority];
    return (
      <div
        key={task.id}
        className={`group rounded-2xl border p-4 transition-all flex items-start gap-3.5 ${
          isDone
            ? 'bg-slate-50/70 border-slate-200/80 opacity-85'
            : 'bg-white border-slate-200 hover:border-blue-300 shadow-2xs'
        }`}
      >
        <button
          type="button"
          onClick={() => toggleMut.mutate(task.id)}
          aria-label={isDone ? `Mark "${task.title}" as pending` : `Mark "${task.title}" as completed`}
          className="mt-0.5 text-blue-600 hover:text-blue-700 transition-colors shrink-0 cursor-pointer"
        >
          {isDone ? (
            <CheckCircle2 size={20} className="text-emerald-600" />
          ) : (
            <Circle size={20} className="text-slate-400 hover:text-blue-600" />
          )}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4
              className={`text-sm font-semibold truncate ${
                isDone ? 'line-through text-slate-500' : 'text-slate-900'
              }`}
            >
              {task.title}
            </h4>
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full border ${prio.cls}`}
            >
              <Flag size={10} />
              {prio.label}
            </span>
          </div>

          {task.notes && (
            <p className="text-xs text-slate-600 mt-1.5 whitespace-pre-wrap leading-relaxed">
              {task.notes}
            </p>
          )}

          {task.due_at && (
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 mt-2">
              <Calendar size={12} className="text-blue-600 shrink-0" />
              <span>Due: {formatDateTime12h(task.due_at)}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => openEditModal(task)}
            title="Edit task"
            aria-label={`Edit "${task.title}"`}
            className="p-1.5 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors cursor-pointer"
          >
            <Pencil size={15} />
          </button>
          <button
            type="button"
            onClick={() => deleteMut.mutate(task.id)}
            title="Delete task"
            aria-label={`Delete "${task.title}"`}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          title="My Tasks"
          subtitle="Your private personal to-do list and notepad. Only visible to you."
        />
        <button
          type="button"
          onClick={openCreateModal}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-colors self-start sm:self-auto cursor-pointer"
        >
          <Plus size={16} />
          <span>Add Task</span>
        </button>
      </div>

      {/* Filter & Sort Bar */}
      <div className="bg-white border border-slate-200 rounded-2xl p-3.5 shadow-2xs flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Filter tasks or notes..."
            className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value as TaskPriority | 'ALL')}
            aria-label="Filter by priority"
            className="text-xs px-3 py-2 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="ALL">All Priorities</option>
            <option value="HIGH">High Priority</option>
            <option value="MEDIUM">Medium Priority</option>
            <option value="LOW">Low Priority</option>
          </select>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as TaskSortBy)}
            aria-label="Sort tasks"
            className="text-xs px-3 py-2 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="created_at">Newest First</option>
            <option value="due_at">Sort by Due Date</option>
            <option value="priority">Sort by Priority</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="py-12 flex justify-center">
          <LoadingState message="Loading your personal tasks..." />
        </div>
      ) : filteredTasks.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-10">
          <EmptyState
            icon={<StickyNote size={28} className="text-blue-600" />}
            title="No tasks yet"
            description="Create a personal task or quick note to keep track of your classes, assignments, and reminders."
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Pending Tasks */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                <CheckSquare size={14} className="text-blue-600" />
                Pending Tasks ({pendingTasks.length})
              </h3>
            </div>
            {pendingTasks.length === 0 ? (
              <p className="text-xs text-slate-400 bg-white border border-slate-200 rounded-xl px-4 py-3">
                All caught up! No pending tasks.
              </p>
            ) : (
              <div className="space-y-2.5">{pendingTasks.map(renderTaskCard)}</div>
            )}
          </section>

          {/* Completed Tasks */}
          {completedTasks.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                <CheckCircle2 size={14} className="text-emerald-600" />
                Completed ({completedTasks.length})
              </h3>
              <div className="space-y-2.5">{completedTasks.map(renderTaskCard)}</div>
            </section>
          )}
        </div>
      )}

      {/* Add / Edit Task Modal */}
      {modalOpen && (
        <FormModal
          isOpen={true}
          title={editingTask ? 'Edit Task' : 'Add New Task'}
          onClose={closeModal}
        >
          <form onSubmit={handleSave} className="space-y-4">
            {formError && (
              <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
                {formError}
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Title <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder="e.g., Prepare lecture slides for Monday"
                className="w-full text-sm px-3 py-2 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Notes / Description
              </label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={4000}
                placeholder="Add details, links, or reminders..."
                className="w-full text-sm px-3 py-2 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Due Date (Optional)
                </label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full text-xs px-3 py-2 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Due Time
                </label>
                <input
                  type="time"
                  value={dueTime}
                  onChange={(e) => setDueTime(e.target.value)}
                  disabled={!dueDate}
                  className="w-full text-xs px-3 py-2 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Priority
                </label>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as TaskPriority)}
                  className="w-full text-xs px-3 py-2 bg-white border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={closeModal}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMut.isPending || updateMut.isPending}
                className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow-xs transition-colors disabled:opacity-50"
              >
                {editingTask ? 'Save Changes' : 'Create Task'}
              </button>
            </div>
          </form>
        </FormModal>
      )}
    </div>
  );
};
