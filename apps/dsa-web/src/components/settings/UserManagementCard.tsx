import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, Shield, User, ToggleLeft, ToggleRight, Coins } from 'lucide-react';
import { authApi, type UserInfo } from '../../api/auth';
import { getParsedApiError } from '../../api/error';
import { Button } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

type UserManagementCardProps = {
  className?: string;
};

export const UserManagementCard: React.FC<UserManagementCardProps> = ({ className }) => {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Create user form
  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');
  const [newEmail, setNewEmail] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Reset password
  const [resetUserId, setResetUserId] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState('');
  const [isResetting, setIsResetting] = useState(false);

  // Edit points
  const [editPointsUserId, setEditPointsUserId] = useState<number | null>(null);
  const [editPointsValue, setEditPointsValue] = useState('');
  const [editPointsReason, setEditPointsReason] = useState('');
  const [isSavingPoints, setIsSavingPoints] = useState(false);

  const loadUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await authApi.listUsers();
      setUsers(result.users);
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '加载用户列表失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const clearMessages = () => {
    setError(null);
    setSuccessMsg(null);
  };

  const handleCreateUser = async () => {
    if (!newUsername.trim() || !newPassword.trim()) {
      setError('用户名和密码不能为空');
      return;
    }
    if (newPassword !== newPasswordConfirm) {
      setError('两次输入的密码不一致');
      return;
    }
    setIsCreating(true);
    clearMessages();
    try {
      await authApi.createUser(newUsername.trim(), newPassword, newPasswordConfirm, newRole, newEmail.trim() || undefined);
      setSuccessMsg(`用户 ${newUsername.trim()} 创建成功`);
      setNewUsername('');
      setNewPassword('');
      setNewPasswordConfirm('');
      setNewRole('user');
      setNewEmail('');
      setShowCreate(false);
      await loadUsers();
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '创建用户失败');
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteUser = async (userId: number, username: string) => {
    if (!confirm(`确认删除用户 "${username}"？此操作不可撤销。`)) return;
    clearMessages();
    try {
      await authApi.deleteUser(userId);
      setSuccessMsg(`用户 ${username} 已删除`);
      await loadUsers();
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '删除用户失败');
    }
  };

  const handleToggleActive = async (userId: number, currentActive: boolean, username: string) => {
    clearMessages();
    try {
      await authApi.updateUser(userId, { isActive: !currentActive });
      setSuccessMsg(`用户 ${username} 已${currentActive ? '禁用' : '启用'}`);
      await loadUsers();
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '更新用户状态失败');
    }
  };

  const handleResetPassword = async () => {
    if (!resetPassword.trim()) {
      setError('新密码不能为空');
      return;
    }
    if (resetPassword !== resetPasswordConfirm) {
      setError('两次输入的密码不一致');
      return;
    }
    if (resetUserId === null) return;
    setIsResetting(true);
    clearMessages();
    try {
      await authApi.resetUserPassword(resetUserId, resetPassword, resetPasswordConfirm);
      setSuccessMsg('密码重置成功');
      setResetUserId(null);
      setResetPassword('');
      setResetPasswordConfirm('');
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '重置密码失败');
    } finally {
      setIsResetting(false);
    }
  };

  const handleRoleChange = async (userId: number, newRole: string, username: string) => {
    clearMessages();
    try {
      await authApi.updateUser(userId, { role: newRole });
      setSuccessMsg(`用户 ${username} 角色已更改为 ${newRole === 'admin' ? '管理员' : '普通用户'}`);
      await loadUsers();
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '更新用户角色失败');
    }
  };

  const handleSavePoints = async () => {
    if (editPointsUserId === null) return;
    const balance = parseInt(editPointsValue, 10);
    if (isNaN(balance)) {
      setError('请输入有效的积分数值');
      return;
    }
    setIsSavingPoints(true);
    clearMessages();
    try {
      await authApi.setUserPoints(editPointsUserId, balance, editPointsReason || undefined);
      setSuccessMsg('积分修改成功');
      setEditPointsUserId(null);
      setEditPointsValue('');
      setEditPointsReason('');
      await loadUsers();
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed.message || '修改积分失败');
    } finally {
      setIsSavingPoints(false);
    }
  };

  return (
    <SettingsSectionCard
      title="用户管理"
      description="管理系统用户账户、角色和密码。"
      className={className}
    >
      <div className="space-y-4">
        {/* Action bar */}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="settings-primary"
            onClick={() => setShowCreate(!showCreate)}
            disabled={isLoading}
          >
            <Plus className="mr-1 h-4 w-4" />
            添加用户
          </Button>
          <Button
            type="button"
            variant="settings-secondary"
            onClick={() => void loadUsers()}
            disabled={isLoading}
            isLoading={isLoading}
            loadingText="加载中..."
          >
            <RefreshCw className="mr-1 h-4 w-4" />
            刷新
          </Button>
        </div>

        {/* Messages */}
        {error && <SettingsAlert title="操作失败" message={error} variant="error" />}
        {successMsg && <SettingsAlert title="操作成功" message={successMsg} variant="success" />}

        {/* Create user form */}
        {showCreate && (
          <div className="rounded-2xl border border-border/50 bg-background/40 p-4 space-y-3">
            <h4 className="text-sm font-medium text-foreground">新建用户</h4>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-muted-text">用户名</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="请输入用户名"
                  disabled={isCreating}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-text">邮箱（可选）</label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="user@example.com"
                  disabled={isCreating}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-text">密码</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="至少 6 位"
                  disabled={isCreating}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-text">确认密码</label>
                <input
                  type="password"
                  value={newPasswordConfirm}
                  onChange={(e) => setNewPasswordConfirm(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="再次确认密码"
                  disabled={isCreating}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-text">角色</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as 'admin' | 'user')}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-[hsl(var(--primary))] focus:outline-none"
                  disabled={isCreating}
                >
                  <option value="user">普通用户</option>
                  <option value="admin">管理员</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="settings-primary"
                onClick={() => void handleCreateUser()}
                disabled={isCreating}
                isLoading={isCreating}
                loadingText="创建中..."
              >
                创建用户
              </Button>
              <Button
                type="button"
                variant="settings-secondary"
                onClick={() => {
                  setShowCreate(false);
                  setNewUsername('');
                  setNewPassword('');
                  setNewPasswordConfirm('');
                  setNewRole('user');
                  setNewEmail('');
                  clearMessages();
                }}
                disabled={isCreating}
              >
                取消
              </Button>
            </div>
          </div>
        )}

        {/* Reset password dialog */}
        {resetUserId !== null && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
            <h4 className="text-sm font-medium text-foreground">重置密码</h4>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-muted-text">新密码</label>
                <input
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="至少 6 位"
                  disabled={isResetting}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-text">确认新密码</label>
                <input
                  type="password"
                  value={resetPasswordConfirm}
                  onChange={(e) => setResetPasswordConfirm(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="再次确认新密码"
                  disabled={isResetting}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="settings-primary"
                onClick={() => void handleResetPassword()}
                disabled={isResetting}
                isLoading={isResetting}
                loadingText="重置中..."
              >
                确认重置
              </Button>
              <Button
                type="button"
                variant="settings-secondary"
                onClick={() => {
                  setResetUserId(null);
                  setResetPassword('');
                  setResetPasswordConfirm('');
                  clearMessages();
                }}
                disabled={isResetting}
              >
                取消
              </Button>
            </div>
          </div>
        )}

        {/* Edit points dialog */}
        {editPointsUserId !== null && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
            <h4 className="text-sm font-medium text-foreground">修改积分</h4>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-muted-text">积分余额</label>
                <input
                  type="number"
                  value={editPointsValue}
                  onChange={(e) => setEditPointsValue(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="输入新的积分值"
                  disabled={isSavingPoints}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-text">备注（可选）</label>
                <input
                  type="text"
                  value={editPointsReason}
                  onChange={(e) => setEditPointsReason(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-text focus:border-[hsl(var(--primary))] focus:outline-none"
                  placeholder="修改原因"
                  disabled={isSavingPoints}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="settings-primary"
                onClick={() => void handleSavePoints()}
                disabled={isSavingPoints}
                isLoading={isSavingPoints}
                loadingText="保存中..."
              >
                确认修改
              </Button>
              <Button
                type="button"
                variant="settings-secondary"
                onClick={() => {
                  setEditPointsUserId(null);
                  setEditPointsValue('');
                  setEditPointsReason('');
                  clearMessages();
                }}
                disabled={isSavingPoints}
              >
                取消
              </Button>
            </div>
          </div>
        )}

        {/* User list */}
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-text">加载用户列表...</div>
        ) : users.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-text">暂无用户</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs uppercase tracking-wider text-muted-text">
                  <th className="px-3 py-2">用户名</th>
                  <th className="px-3 py-2">角色</th>
                  <th className="px-3 py-2">积分</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2">创建时间</th>
                  <th className="px-3 py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {users.map((user) => (
                  <tr key={user.id} className="hover:bg-hover/30">
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        {user.role === 'admin' ? (
                          <Shield className="h-4 w-4 text-amber-500" />
                        ) : (
                          <User className="h-4 w-4 text-muted-text" />
                        )}
                        <span className="font-medium text-foreground">{user.username}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <select
                        value={user.role}
                        onChange={(e) => void handleRoleChange(user.id, e.target.value, user.username)}
                        className="rounded border border-border/50 bg-transparent px-2 py-1 text-xs text-foreground focus:border-[hsl(var(--primary))] focus:outline-none"
                      >
                        <option value="admin">管理员</option>
                        <option value="user">普通用户</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1">
                        <Coins className="h-3.5 w-3.5 text-amber-500" />
                        <span className={`text-xs font-medium ${(user.pointsBalance ?? 0) < 0 ? 'text-red-500' : 'text-foreground'}`}>
                          {user.pointsBalance ?? 0}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        onClick={() => void handleToggleActive(user.id, user.isActive, user.username)}
                        className="flex items-center gap-1 text-xs"
                        title={user.isActive ? '点击禁用' : '点击启用'}
                      >
                        {user.isActive ? (
                          <>
                            <ToggleRight className="h-5 w-5 text-emerald-500" />
                            <span className="text-emerald-600 dark:text-emerald-400">启用</span>
                          </>
                        ) : (
                          <>
                            <ToggleLeft className="h-5 w-5 text-muted-text" />
                            <span className="text-muted-text">禁用</span>
                          </>
                        )}
                      </button>
                    </td>
                    <td className="px-3 py-3 text-xs text-muted-text">
                      {user.createdAt ? new Date(user.createdAt).toLocaleDateString('zh-CN') : '-'}
                    </td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setEditPointsUserId(user.id);
                            setEditPointsValue(String(user.pointsBalance ?? 0));
                            setEditPointsReason('');
                            clearMessages();
                          }}
                          className="rounded-lg px-2 py-1 text-xs text-amber-600 hover:bg-amber-500/10 transition-colors"
                          title="修改积分"
                        >
                          <Coins className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setResetUserId(user.id);
                            setResetPassword('');
                            setResetPasswordConfirm('');
                            clearMessages();
                          }}
                          className="rounded-lg px-2 py-1 text-xs text-[hsl(var(--primary))] hover:bg-hover transition-colors"
                          title="重置密码"
                        >
                          重置密码
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDeleteUser(user.id, user.username)}
                          className="rounded-lg px-2 py-1 text-xs text-red-500 hover:bg-red-500/10 transition-colors"
                          title="删除用户"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SettingsSectionCard>
  );
};
