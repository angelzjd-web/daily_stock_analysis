import React, { useState } from 'react';
import { motion } from 'motion/react';
import { BarChart3, BriefcaseBusiness, Bell, Coins, Home, LogOut, MessageSquareQuote, Settings2, UserCircle } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { cn } from '../../utils/cn';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { StatusDot } from '../common/StatusDot';
import { ThemeToggle } from '../theme/ThemeToggle';

type SidebarNavProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
};

type NavItem = {
  key: string;
  label: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: 'completion';
  adminOnly?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { key: 'home', label: '首页', to: '/', icon: Home, exact: true },
  { key: 'chat', label: '问股', to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'portfolio', label: '持仓', to: '/portfolio', icon: BriefcaseBusiness },
  { key: 'backtest', label: '回测', to: '/backtest', icon: BarChart3 },
  { key: 'notification', label: '通知', to: '/notification', icon: Bell },
  { key: 'settings', label: '设置', to: '/settings', icon: Settings2, adminOnly: true },
];

export const SidebarNav: React.FC<SidebarNavProps> = ({ collapsed = false, onNavigate }) => {
  const { authEnabled, isAdmin, currentUser, logout } = useAuth();
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (item.adminOnly && !isAdmin) return false;
    return true;
  });

  return (
    <div className="flex h-full flex-col">
      <div className={cn('mb-4 flex items-center gap-2 px-1', collapsed ? 'justify-center' : '')}>
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary-gradient text-[hsl(var(--primary-foreground))] shadow-[0_12px_28px_var(--nav-brand-shadow)]">
          <BarChart3 className="h-5 w-5" />
        </div>
        {!collapsed ? (
          <p className="min-w-0 truncate text-sm font-semibold text-foreground">DSA</p>
        ) : null}
      </div>

      <nav className="flex flex-1 flex-col gap-1.5" aria-label="主导航">
        {visibleItems.map(({ key, label, to, icon: Icon, exact, badge }) => (
          <NavLink
            key={key}
            to={to}
            end={exact}
            onClick={onNavigate}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                'group relative flex items-center gap-3 border-y border-x-0 text-sm transition-all',
                'h-[var(--nav-item-height)]',
                collapsed ? 'justify-center px-0' : 'px-[var(--nav-item-padding-x)]',
                isActive
                  ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-[hsl(var(--primary))] font-medium'
                  : 'border-transparent text-secondary-text hover:bg-[var(--nav-hover-bg)] hover:text-foreground'
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div 
                    layoutId="activeIndicator"
                    className="absolute top-0 bottom-0 left-0 w-[var(--nav-indicator-width)] bg-[var(--nav-indicator-bg)] shadow-[0_0_10px_var(--nav-indicator-shadow)]"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2 }}
                  />
                )}
                <Icon className={cn('ml-1 h-5 w-5 shrink-0', isActive ? 'text-[var(--nav-icon-active)]' : 'text-current')} />
                {!collapsed ? <span className="truncate">{label}</span> : null}
                {badge === 'completion' && completionBadge ? (
                  <StatusDot
                    tone="info"
                    data-testid="chat-completion-badge"
                    className={cn(
                      'absolute right-3 border-2 border-background shadow-[0_0_10px_var(--nav-indicator-shadow)]',
                      collapsed ? 'right-2 top-2' : ''
                    )}
                    aria-label="问股有新消息"
                  />
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Current user info */}
      {authEnabled && currentUser && !collapsed ? (
        <div className="mb-2 flex items-center gap-2 rounded-xl border border-border/50 bg-hover/50 px-3 py-2">
          <UserCircle className="h-5 w-5 shrink-0 text-secondary-text" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-foreground">{currentUser.username}</p>
            <div className="flex items-center gap-1">
              <p className="text-[10px] text-muted-text">{currentUser.role === 'admin' ? '管理员' : '用户'}</p>
              <span className="text-[10px] text-muted-text">·</span>
              <div className="flex items-center gap-0.5">
                <Coins className="h-3 w-3 text-amber-500" />
                <span className={`text-[10px] ${(currentUser.pointsBalance ?? 0) < 0 ? 'text-red-500' : 'text-muted-text'}`}>
                  {currentUser.pointsBalance ?? 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-4 mb-2">
        <ThemeToggle variant="nav" collapsed={collapsed} />
      </div>

      {authEnabled ? (
        <button
          type="button"
          onClick={() => setShowLogoutConfirm(true)}
          className={cn(
            'mt-5 flex h-11 w-full cursor-pointer select-none items-center gap-3 rounded-2xl border border-transparent px-3 text-sm text-secondary-text transition-all hover:border-border/70 hover:bg-hover hover:text-foreground',
            collapsed ? 'justify-center px-2' : ''
          )}
        >
          <LogOut className="h-5 w-5 shrink-0" />
          {!collapsed ? <span>退出</span> : null}
        </button>
      ) : null}

      <ConfirmDialog
        isOpen={showLogoutConfirm}
        title="退出登录"
        message="确认退出当前登录状态吗？退出后需要重新输入密码。"
        confirmText="确认退出"
        cancelText="取消"
        isDanger
        onConfirm={() => {
          setShowLogoutConfirm(false);
          onNavigate?.();
          void logout();
        }}
        onCancel={() => setShowLogoutConfirm(false)}
      />
    </div>
  );
};
