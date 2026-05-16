import apiClient from './index';
import { toCamelCase } from './utils';

export interface NotificationConfigItem {
  key: string;
  value: string;
}

export interface NotificationConfigResponse {
  items: NotificationConfigItem[];
  updatedAt?: string | null;
}

export interface UpdateNotificationConfigRequest {
  items: NotificationConfigItem[];
}

export interface UpdateNotificationConfigResponse {
  success: boolean;
  count: number;
}

export interface DeleteNotificationConfigResponse {
  success: boolean;
  deleted: boolean;
}

export const notificationApi = {
  /** 获取当前用户的通知渠道配置 */
  async getConfig(): Promise<NotificationConfigResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/notification/config');
    return toCamelCase<NotificationConfigResponse>(response.data);
  },

  /** 更新当前用户的通知渠道配置（upsert） */
  async updateConfig(payload: UpdateNotificationConfigRequest): Promise<UpdateNotificationConfigResponse> {
    const response = await apiClient.put<Record<string, unknown>>('/api/v1/notification/config', {
      items: payload.items.map((item) => ({ key: item.key, value: item.value })),
    });
    return toCamelCase<UpdateNotificationConfigResponse>(response.data);
  },

  /** 删除当前用户的某项通知配置 */
  async deleteConfig(key: string): Promise<DeleteNotificationConfigResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/notification/config/${encodeURIComponent(key)}`);
    return toCamelCase<DeleteNotificationConfigResponse>(response.data);
  },
};
