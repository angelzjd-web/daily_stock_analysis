import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Send, Trash2 } from 'lucide-react';
import { notificationApi, type NotificationConfigItem } from '../api/notification';
import { systemConfigApi } from '../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type { NotificationTestChannel, SystemConfigFieldSchema, TestNotificationChannelResponse, SystemConfigUpdateItem } from '../types/systemConfig';
import { ApiErrorAlert, Badge, Button, ConfirmDialog, InlineAlert, Input, Select } from '../components/common';
import { SettingsSectionCard } from '../components/settings/SettingsSectionCard';
import { SettingsField } from '../components/settings/SettingsField';
import { getFieldTitleZh, getFieldDescriptionZh } from '../utils/systemConfigI18n';

// ============ 通知渠道选项 ============

const CHANNEL_OPTIONS: Array<{ value: NotificationTestChannel; label: string }> = [
  { value: 'wechat', label: '企业微信' },
  { value: 'feishu', label: '飞书 Webhook' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'email', label: '邮件' },
  { value: 'pushover', label: 'Pushover' },
  { value: 'ntfy', label: 'ntfy' },
  { value: 'gotify', label: 'Gotify' },
  { value: 'pushplus', label: 'PushPlus' },
  { value: 'serverchan3', label: 'Server酱3' },
  { value: 'custom', label: '自定义 Webhook' },
  { value: 'discord', label: 'Discord' },
  { value: 'slack', label: 'Slack' },
  { value: 'astrbot', label: 'AstrBot' },
];

// ============ 按渠道分组的字段 ============

const CHANNEL_GROUPS: Record<string, { title: string; keys: string[] }> = {
  wechat: { title: '企业微信', keys: ['WECHAT_WEBHOOK_URL'] },
  feishu: { title: '飞书', keys: ['FEISHU_WEBHOOK_URL', 'FEISHU_WEBHOOK_SECRET', 'FEISHU_WEBHOOK_KEYWORD', 'FEISHU_APP_ID', 'FEISHU_APP_SECRET'] },
  dingtalk: { title: '钉钉', keys: ['DINGTALK_APP_KEY', 'DINGTALK_APP_SECRET'] },
  telegram: { title: 'Telegram', keys: ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'TELEGRAM_MESSAGE_THREAD_ID'] },
  email: { title: '邮件', keys: ['EMAIL_SENDER', 'EMAIL_PASSWORD', 'EMAIL_RECEIVERS'] },
  pushplus: { title: 'PushPlus', keys: ['PUSHPLUS_TOKEN', 'PUSHPLUS_TOPIC'] },
  ntfy: { title: 'ntfy', keys: ['NTFY_URL', 'NTFY_TOKEN'] },
  gotify: { title: 'Gotify', keys: ['GOTIFY_URL', 'GOTIFY_TOKEN'] },
  serverchan3: { title: 'Server酱3', keys: ['SERVERCHAN3_SENDKEY'] },
  custom: { title: '自定义 Webhook', keys: ['CUSTOM_WEBHOOK_URLS', 'CUSTOM_WEBHOOK_BEARER_TOKEN', 'CUSTOM_WEBHOOK_BODY_TEMPLATE', 'WEBHOOK_VERIFY_SSL'] },
  pushover: { title: 'Pushover', keys: ['PUSHOVER_USER_KEY', 'PUSHOVER_API_TOKEN'] },
  discord: { title: 'Discord', keys: ['DISCORD_WEBHOOK_URL', 'DISCORD_BOT_TOKEN', 'DISCORD_MAIN_CHANNEL_ID', 'DISCORD_INTERACTIONS_PUBLIC_KEY'] },
  slack: { title: 'Slack', keys: ['SLACK_BOT_TOKEN', 'SLACK_CHANNEL_ID', 'SLACK_WEBHOOK_URL'] },
  astrbot: { title: 'AstrBot', keys: ['ASTRBOT_URL', 'ASTRBOT_TOKEN'] },
};

// 通用配置（不属于特定渠道）
const COMMON_KEYS = [
  'SINGLE_STOCK_NOTIFY',
  'REPORT_TYPE',
  'REPORT_LANGUAGE',
  'REPORT_SUMMARY_ONLY',
  'NOTIFICATION_REPORT_CHANNELS',
  'NOTIFICATION_ALERT_CHANNELS',
  'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
  'NOTIFICATION_DEDUP_TTL_SECONDS',
  'NOTIFICATION_COOLDOWN_SECONDS',
  'NOTIFICATION_QUIET_HOURS',
  'NOTIFICATION_TIMEZONE',
  'NOTIFICATION_MIN_SEVERITY',
  'NOTIFICATION_DAILY_DIGEST_ENABLED',
  'MERGE_EMAIL_NOTIFICATION',
  'REPORT_TEMPLATES_DIR',
  'REPORT_RENDERER_ENABLED',
  'REPORT_INTEGRITY_ENABLED',
  'REPORT_INTEGRITY_RETRY',
  'REPORT_HISTORY_COMPARE_N',
];

function clampTimeout(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 20;
  return Math.min(120, Math.max(1, parsed));
}

// ============ 通知渠道页面 ============

const NotificationPage: React.FC = () => {

  // 配置状态
  const [configItems, setConfigItems] = useState<NotificationConfigItem[]>([]);
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [schemaMap, setSchemaMap] = useState<Record<string, SystemConfigFieldSchema>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [saveError, setSaveError] = useState<ParsedApiError | null>(null);
  const [saveSuccess, setSaveSuccess] = useState('');

  // 测试状态
  const [testChannel, setTestChannel] = useState<NotificationTestChannel>('wechat');
  const [testTitle, setTestTitle] = useState('DSA 通知测试');
  const [testContent, setTestContent] = useState('这是一条来自通知渠道页面的测试消息。');
  const [testTimeout, setTestTimeout] = useState('20');
  const [testResult, setTestResult] = useState<TestNotificationChannelResponse | null>(null);
  const [testError, setTestError] = useState<ParsedApiError | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  // 删除确认
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // 展开的渠道
  const [expandedChannels, setExpandedChannels] = useState<Set<string>>(new Set());

  useEffect(() => {
    document.title = '通知渠道 - DSA';
  }, []);

  // 加载配置
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      // 并行获取用户配置和 schema
      const [configResp, schemaResp] = await Promise.all([
        notificationApi.getConfig(),
        systemConfigApi.getSchema(),
      ]);
      setConfigItems(configResp.items);

      // 构建 draftValues: 用户已保存的值 + schema 默认值
      const userMap: Record<string, string> = {};
      for (const item of configResp.items) {
        userMap[item.key] = item.value;
      }
      const schemaFields: Record<string, SystemConfigFieldSchema> = {};
      for (const cat of schemaResp.categories) {
        if (cat.category === 'notification') {
          for (const field of cat.fields) {
            schemaFields[field.key] = field;
            // 用户有值用用户的，否则用 schema 默认值
            if (!(field.key in userMap) && field.defaultValue) {
              userMap[field.key] = field.defaultValue;
            }
          }
        }
      }
      setSchemaMap(schemaFields);
      setDraftValues(userMap);

      // 自动展开有内容的渠道
      const expanded = new Set<string>();
      for (const [channelId, group] of Object.entries(CHANNEL_GROUPS)) {
        if (group.keys.some((k) => userMap[k]?.trim())) {
          expanded.add(channelId);
        }
      }
      setExpandedChannels(expanded);
    } catch (err) {
      setLoadError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // 保存
  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess('');
    try {
      // 只提交有改动的或非空的项目
      const items = Object.entries(draftValues)
        .filter(([, value]) => value.trim() !== '')
        .map(([key, value]) => ({ key, value }));
      await notificationApi.updateConfig({ items });
      setSaveSuccess('通知渠道配置已保存。');
      // 重新加载
      await loadData();
    } catch (err) {
      setSaveError(getParsedApiError(err));
    } finally {
      setIsSaving(false);
    }
  };

  // 测试
  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const items: SystemConfigUpdateItem[] = Object.entries(draftValues)
        .filter(([, value]) => value.trim())
        .map(([key, value]) => ({ key, value }));
      const result = await systemConfigApi.testNotificationChannel({
        channel: testChannel,
        items,
        maskToken: '******',
        title: testTitle.trim() || 'DSA 通知测试',
        content: testContent.trim() || '这是一条来自通知渠道页面的测试消息。',
        timeoutSeconds: clampTimeout(testTimeout),
      });
      setTestResult(result);
    } catch (err) {
      setTestError(getParsedApiError(err));
    } finally {
      setIsTesting(false);
    }
  };

  // 删除单项
  const handleDelete = async (key: string) => {
    try {
      await notificationApi.deleteConfig(key);
      setDraftValues((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setConfigItems((prev) => prev.filter((item) => item.key !== key));
    } catch (err) {
      console.error('删除配置项失败:', err);
    }
    setShowDeleteConfirm(false);
    setDeleteKey(null);
  };

  // dirty 检测
  const hasDirty = useMemo(() => {
    const savedMap: Record<string, string> = {};
    for (const item of configItems) {
      savedMap[item.key] = item.value;
    }
    // 新增或有修改
    for (const [key, value] of Object.entries(draftValues)) {
      if (value.trim() && (savedMap[key] === undefined || savedMap[key] !== value)) {
        return true;
      }
    }
    return false;
  }, [draftValues, configItems]);

  // 渠道是否有内容
  const isChannelConfigured = (channelId: string): boolean => {
    const group = CHANNEL_GROUPS[channelId];
    if (!group) return false;
    return group.keys.some((k) => draftValues[k]?.trim());
  };

  const toggleChannel = (channelId: string) => {
    setExpandedChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channelId)) {
        next.delete(channelId);
      } else {
        next.add(channelId);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="min-h-full px-4 pb-6 pt-4 md:px-6">
        <ApiErrorAlert error={loadError} actionLabel="重试" onAction={() => void loadData()} />
      </div>
    );
  }

  return (
    <div className="min-h-full px-4 pb-6 pt-4 md:px-6">
      {/* 页面标题 */}
      <div className="mb-5 rounded-[1.5rem] border settings-border bg-card/94 px-5 py-5 shadow-soft-card-strong backdrop-blur-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">通知渠道</h1>
            <p className="text-xs leading-6 text-muted-text">
              配置个人通知渠道凭据与推送偏好。所有数据仅属于当前用户。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="settings-secondary"
              onClick={() => void loadData()}
              disabled={isLoading || isSaving}
            >
              刷新
            </Button>
            <Button
              type="button"
              variant="settings-primary"
              onClick={() => void handleSave()}
              disabled={!hasDirty || isSaving || isLoading}
              isLoading={isSaving}
              loadingText="保存中..."
            >
              保存配置
            </Button>
          </div>
        </div>

        {saveError ? (
          <ApiErrorAlert className="mt-3" error={saveError} />
        ) : null}
        {saveSuccess ? (
          <InlineAlert className="mt-3" variant="success" title="保存成功" message={saveSuccess} />
        ) : null}
      </div>

      {/* 渠道配置卡片 */}
      <div className="space-y-4">
        {Object.entries(CHANNEL_GROUPS).map(([channelId, group]) => {
          const isExpanded = expandedChannels.has(channelId);
          const isConfigured = isChannelConfigured(channelId);
          const channelOption = CHANNEL_OPTIONS.find((o) => o.value === channelId);
          const channelLabel = channelOption?.label || group.title;

          return (
            <SettingsSectionCard
              key={channelId}
              title={channelLabel}
              description={isConfigured ? '已配置' : '未配置'}
              actions={
                <div className="flex items-center gap-2">
                  {isConfigured ? (
                    <Badge variant="success">已配置</Badge>
                  ) : (
                    <Badge variant="default">未配置</Badge>
                  )}
                  <Button
                    type="button"
                    variant="settings-secondary"
                    size="sm"
                    onClick={() => toggleChannel(channelId)}
                  >
                    {isExpanded ? '收起' : '展开'}
                  </Button>
                </div>
              }
            >
              {isExpanded ? (
                <div className="space-y-3">
                  {group.keys.map((key) => {
                    const schema = schemaMap[key];
                    const item = schema
                      ? {
                          key,
                          value: draftValues[key] ?? '',
                          rawValueExists: Boolean(draftValues[key]),
                          isMasked: false,
                          schema,
                        }
                      : {
                          key,
                          value: draftValues[key] ?? '',
                          rawValueExists: Boolean(draftValues[key]),
                          isMasked: false,
                          schema: {
                            key,
                            title: getFieldTitleZh(key, key),
                            description: getFieldDescriptionZh(key, ''),
                            category: 'notification' as const,
                            dataType: 'string' as const,
                            uiControl: (key.includes('SECRET') || key.includes('TOKEN') || key.includes('PASSWORD') || key.includes('KEY') || key.includes('SENDKEY') || key.includes('API_TOKEN'))
                              ? 'password' as const
                              : 'text' as const,
                            isSensitive: key.includes('SECRET') || key.includes('TOKEN') || key.includes('PASSWORD') || key.includes('KEY'),
                            isRequired: false,
                            isEditable: true,
                            options: [],
                            validation: {},
                            displayOrder: 0,
                          },
                        };

                    return (
                      <div key={key} className="flex items-start gap-2">
                        <div className="flex-1">
                          <SettingsField
                            item={item}
                            value={item.value}
                            disabled={isSaving}
                            onChange={(_key: string, value: string) => {
                              setDraftValues((prev) => ({ ...prev, [_key]: value }));
                            }}
                            issues={[]}
                          />
                        </div>
                        {draftValues[key]?.trim() && (
                          <button
                            type="button"
                            onClick={() => {
                              setDeleteKey(key);
                              setShowDeleteConfirm(true);
                            }}
                            className="mt-7 flex-shrink-0 rounded-lg p-2 text-muted-text transition-colors hover:bg-hover hover:text-danger"
                            title="清除此配置项"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-muted-text py-1">
                  点击"展开"查看和编辑 {channelLabel} 的配置项。
                </p>
              )}
            </SettingsSectionCard>
          );
        })}

        {/* 通用配置 */}
        <SettingsSectionCard
          title="推送与报告配置"
          description="通知路由、去重、静默时段和报告格式等通用设置。"
        >
          <div className="space-y-3">
            {COMMON_KEYS.map((key) => {
              const schema = schemaMap[key];
              if (!schema) return null;

              const item = {
                key,
                value: draftValues[key] ?? '',
                rawValueExists: Boolean(draftValues[key]),
                isMasked: false,
                schema,
              };

              return (
                <SettingsField
                  key={key}
                  item={item}
                  value={item.value}
                  disabled={isSaving}
                  onChange={(_key: string, value: string) => {
                    setDraftValues((prev) => ({ ...prev, [_key]: value }));
                  }}
                  issues={[]}
                />
              );
            })}
          </div>
        </SettingsSectionCard>

        {/* 测试面板 */}
        <SettingsSectionCard
          title="通知测试"
          description="使用当前页面草稿发送一条真实测试通知；测试不会保存配置。"
          actions={
            <Button
              type="button"
              variant="settings-primary"
              size="sm"
              onClick={() => void handleTest()}
              disabled={isSaving || isTesting}
              isLoading={isTesting}
              loadingText="测试中..."
            >
              <Send className="h-4 w-4" />
              发送测试
            </Button>
          }
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_120px]">
            <Select
              label="渠道"
              value={testChannel}
              options={CHANNEL_OPTIONS}
              disabled={isTesting}
              onChange={(value) => setTestChannel(value as NotificationTestChannel)}
            />
            <Input
              label="标题"
              value={testTitle}
              maxLength={80}
              disabled={isTesting}
              onChange={(event) => setTestTitle(event.target.value)}
            />
            <Input
              label="超时秒数"
              type="number"
              min={1}
              max={120}
              value={testTimeout}
              disabled={isTesting}
              onChange={(event) => setTestTimeout(event.target.value)}
              onBlur={() => setTestTimeout(String(clampTimeout(testTimeout)))}
            />
          </div>

          <label className="block mt-3">
            <span className="mb-2 block text-sm font-medium text-foreground">正文</span>
            <textarea
              value={testContent}
              maxLength={1000}
              rows={4}
              disabled={isTesting}
              onChange={(event) => setTestContent(event.target.value)}
              className="input-surface input-focus-glow min-h-[112px] w-full resize-y rounded-xl border bg-transparent px-4 py-3 text-sm leading-6 text-foreground outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
          </label>

          {testError ? <ApiErrorAlert error={testError} className="mt-3" /> : null}

          {testResult ? (
            <div className="space-y-3 mt-3">
              <InlineAlert
                variant={testResult.success ? 'success' : 'danger'}
                title={testResult.success ? '测试成功' : '测试失败'}
                message={(
                  <span>
                    {testResult.message}
                    {typeof testResult.latencyMs === 'number' ? ` · ${testResult.latencyMs} ms` : ''}
                    {testResult.errorCode ? ` · ${testResult.errorCode}` : ''}
                  </span>
                )}
              />

              {testResult.attempts.length ? (
                <div className="space-y-2">
                  {testResult.attempts.map((attempt, index) => (
                    <div
                      key={`${attempt.channel}-${index}-${attempt.target || 'target'}`}
                      className="rounded-xl border settings-border bg-background/35 px-4 py-3"
                    >
                      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={attempt.success ? 'success' : 'danger'}>
                              {attempt.success ? '成功' : '失败'}
                            </Badge>
                            <span className="text-sm font-medium text-foreground">
                              第 {index + 1} 次尝试
                            </span>
                            {typeof attempt.httpStatus === 'number' ? (
                              <span className="text-xs text-muted-text">HTTP {attempt.httpStatus}</span>
                            ) : null}
                            {typeof attempt.latencyMs === 'number' ? (
                              <span className="text-xs text-muted-text">{attempt.latencyMs} ms</span>
                            ) : null}
                          </div>
                          <p className="mt-2 break-all text-xs leading-5 text-muted-text">
                            {attempt.target || attempt.channel}
                          </p>
                        </div>
                        {attempt.errorCode ? (
                          <Badge variant={attempt.retryable ? 'warning' : 'default'}>
                            {attempt.errorCode}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-2 text-xs leading-5 text-secondary-text">{attempt.message}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </SettingsSectionCard>
      </div>

      {/* 删除确认对话框 */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        title="清除配置项"
        message={`确认清除「${deleteKey}」的配置？保存后该值将从你的个人配置中删除。`}
        confirmText="确认清除"
        cancelText="取消"
        isDanger
        onConfirm={() => {
          if (deleteKey) {
            void handleDelete(deleteKey);
          }
        }}
        onCancel={() => {
          setShowDeleteConfirm(false);
          setDeleteKey(null);
        }}
      />
    </div>
  );
};

export default NotificationPage;
