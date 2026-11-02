import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Search, KeyRound, Check } from 'lucide-react';
import { isAxiosError } from 'axios';
import {
  DataTable,
  type Column,
  FormModal,
  PageHeader,
  StatusBadge,
} from '@/components/common';
import {
  usersApi,
  type UserAdminItem,
  type UserAdminCreate,
  type UserAdminUpdate,
} from '@/api/users';
import { departmentsApi } from '@/api/departments';

export function UsersPage() {
  const queryClient = useQueryClient();

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Form Modal state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserAdminItem | null>(null);

  // Form Fields
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'ADMIN' | 'FACULTY' | 'STUDENT'>('STUDENT');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [isActive, setIsActive] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  // Reset Password Modal State
  const [isResetOpen, setIsResetOpen] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  // Queries
  const {
    data: users,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['admin-users'],
    queryFn: usersApi.getAll,
  });

  const { data: departments } = useQuery({
    queryKey: ['departments'],
    queryFn: departmentsApi.getAll,
  });

  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  // Mutations
  const createMutation = useMutation({
    mutationFn: (payload: UserAdminCreate) => usersApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      closeForm();
    },
    onError: (err) => setFormError(getErrorMsg(err, 'Failed to create user.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UserAdminUpdate }) =>
      usersApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      closeForm();
    },
    onError: (err) => setFormError(getErrorMsg(err, 'Failed to update user.')),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ id, pwd }: { id: number; pwd: string }) =>
      usersApi.resetPassword(id, pwd),
    onSuccess: () => {
      setResetMsg('Password successfully reset and saved to the database.');
      setTimeout(() => {
        setIsResetOpen(false);
        setSelectedUser(null);
        setNewPassword('');
        setResetMsg(null);
      }, 1500);
    },
    onError: (err) =>
      setFormError(getErrorMsg(err, 'Failed to reset password.')),
  });

  // Filtered dataset
  const filteredData = useMemo(() => {
    if (!users) return [];
    return users.filter((u) => {
      const matchesSearch =
        u.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (u.department_name &&
          u.department_name.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesRole = roleFilter === 'ALL' || u.role === roleFilter;
      const matchesStatus =
        statusFilter === 'ALL' ||
        (statusFilter === 'ACTIVE' && u.is_active) ||
        (statusFilter === 'INACTIVE' && !u.is_active);

      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [users, searchTerm, roleFilter, statusFilter]);

  const openCreateForm = () => {
    setSelectedUser(null);
    setName('');
    setEmail('');
    setPassword('');
    setRole('STUDENT');
    setDepartmentId('');
    setIsActive(true);
    setFormError(null);
    setIsFormOpen(true);
  };

  const openEditForm = (u: UserAdminItem) => {
    setSelectedUser(u);
    setName(u.name);
    setEmail(u.email);
    setPassword('');
    setRole(u.role);
    setDepartmentId(u.department_id || '');
    setIsActive(u.is_active);
    setFormError(null);
    setIsFormOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedUser(null);
    setFormError(null);
  };

  const openResetPasswordModal = (u: UserAdminItem) => {
    setSelectedUser(u);
    setNewPassword('');
    setFormError(null);
    setResetMsg(null);
    setIsResetOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!name.trim() || !email.trim()) {
      setFormError('Full name and email are required.');
      return;
    }

    if (!selectedUser && (!password || password.length < 6)) {
      setFormError('Initial password must be at least 6 characters.');
      return;
    }

    if (selectedUser) {
      updateMutation.mutate({
        id: selectedUser.id,
        payload: {
          name: name.trim(),
          role,
          department_id: departmentId ? Number(departmentId) : null,
          is_active: isActive,
        },
      });
    } else {
      createMutation.mutate({
        email: email.trim(),
        name: name.trim(),
        password,
        role,
        department_id: departmentId ? Number(departmentId) : null,
      });
    }
  };

  const handleResetSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!selectedUser) return;
    if (!newPassword || newPassword.length < 6) {
      setFormError('New password must be at least 6 characters.');
      return;
    }
    resetPasswordMutation.mutate({ id: selectedUser.id, pwd: newPassword });
  };

  const columns: Column<UserAdminItem>[] = [
    {
      header: 'User Details',
      accessor: 'name',
      render: (row) => (
        <div>
          <div className="font-semibold text-slate-900">{row.name}</div>
          <div className="text-xs text-slate-500 font-mono">{row.email}</div>
        </div>
      ),
    },
    {
      header: 'Role',
      accessor: 'role',
      render: (row) => {
        const color =
          row.role === 'ADMIN'
            ? 'bg-purple-100 text-purple-800 border-purple-200'
            : row.role === 'FACULTY'
            ? 'bg-blue-100 text-blue-800 border-blue-200'
            : 'bg-emerald-100 text-emerald-800 border-emerald-200';
        return (
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${color}`}
          >
            {row.role}
          </span>
        );
      },
    },
    {
      header: 'Department',
      accessor: 'department_name',
      render: (row) => (
        <span className="text-sm text-slate-700">
          {row.department_name || '—'}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: 'is_active',
      render: (row) => (
        <StatusBadge
          status={row.is_active ? 'ACTIVE' : 'INACTIVE'}
          variant={row.is_active ? 'success' : 'neutral'}
        />
      ),
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              openEditForm(row);
            }}
            className="px-2.5 py-1 text-xs font-medium text-slate-700 hover:text-primary-700 bg-slate-100 hover:bg-primary-50 rounded-md transition-colors"
          >
            Edit
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              openResetPasswordModal(row);
            }}
            className="p-1 text-slate-500 hover:text-amber-700 hover:bg-amber-50 rounded-md transition-colors"
            title="Reset Password"
          >
            <KeyRound size={16} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users & Roles"
        subtitle="Manage administrative, faculty, and student user accounts, credentials, and access control."
        actions={
          <button
            onClick={openCreateForm}
            className="inline-flex items-center gap-2 px-3.5 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors"
          >
            <Plus size={16} />
            Add User
          </button>
        }
      />

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-[280px]">
          <div className="relative flex-1 max-w-md">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              type="text"
              placeholder="Search by name, email or department…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20"
          >
            <option value="ALL">All Roles</option>
            <option value="ADMIN">Administrators</option>
            <option value="FACULTY">Faculty Members</option>
            <option value="STUDENT">Students</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20"
          >
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">Active Accounts</option>
            <option value="INACTIVE">Deactivated Accounts</option>
          </select>
        </div>
      </div>

      {/* User Directory Table */}
      <DataTable<UserAdminItem>
        columns={columns}
        data={filteredData}
        isLoading={isLoading}
        isError={isError}
        error={error as Error | null}
        onRefresh={refetch}
        keyExtractor={(row) => row.id}
        searchPlaceholder="Filter listed users…"
        emptyMessage={
          searchTerm || roleFilter !== 'ALL'
            ? 'No users match your active filters. Try clearing your search parameters.'
            : 'Create a new user account to get started.'
        }
      />

      {/* Create / Edit User Modal */}
      <FormModal
        isOpen={isFormOpen}
        onClose={closeForm}
        title={selectedUser ? `Edit User: ${selectedUser.name}` : 'Provision New User'}
      >
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {formError}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Full Name *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Dr. Jane Smith"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Institutional Email *
              </label>
              <input
                type="email"
                required
                disabled={!!selectedUser}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. jane.smith@campus.edu"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm disabled:bg-slate-50 disabled:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
              />
            </div>

            {!selectedUser && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Initial Password *
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min 6 characters"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Assigned Role *
                </label>
                <select
                  value={role}
                  onChange={(e) =>
                    setRole(e.target.value as 'ADMIN' | 'FACULTY' | 'STUDENT')
                  }
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                >
                  <option value="STUDENT">STUDENT</option>
                  <option value="FACULTY">FACULTY</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Department
                </label>
                <select
                  value={departmentId}
                  onChange={(e) =>
                    setDepartmentId(e.target.value ? Number(e.target.value) : '')
                  }
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                >
                  <option value="">None / Campus-wide</option>
                  {departments?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.department_code})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {selectedUser && (
              <div className="pt-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={(e) => setIsActive(e.target.checked)}
                    className="rounded text-primary-600 focus:ring-primary-500 h-4 w-4"
                  />
                  <span className="text-sm font-medium text-slate-700">
                    Account is Active (can authenticate and access portals)
                  </span>
                </label>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={closeForm}
              className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
            >
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save User'}
            </button>
          </div>
        </form>
      </FormModal>

      {/* Reset Password Modal */}
      <FormModal
        isOpen={isResetOpen}
        onClose={() => {
          setIsResetOpen(false);
          setSelectedUser(null);
          setFormError(null);
        }}
        title={`Reset Password: ${selectedUser?.email}`}
      >
        <form onSubmit={handleResetSubmit} className="p-6 space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {formError}
            </div>
          )}

          {resetMsg ? (
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-800 font-semibold flex items-center gap-2">
              <Check size={18} className="text-emerald-600" />
              {resetMsg}
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-xs text-slate-600">
                Enter a new secure password for this user. The password will be
                hashed on the backend using bcrypt and updated immediately.
              </p>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  New Password *
                </label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter minimum 6 characters…"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => {
                    setIsResetOpen(false);
                    setSelectedUser(null);
                    setFormError(null);
                  }}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resetPasswordMutation.isPending}
                  className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                >
                  {resetPasswordMutation.isPending ? 'Updating…' : 'Update Password'}
                </button>
              </div>
            </div>
          )}
        </form>
      </FormModal>
    </div>
  );
}
