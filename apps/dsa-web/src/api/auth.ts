import apiClient from './index';

export type AuthStatusResponse = {
  authEnabled: boolean;
  loggedIn: boolean;
  passwordSet?: boolean;
  passwordChangeable?: boolean;
  setupState: 'enabled' | 'password_retained' | 'no_password';
  currentUser?: {
    id: number;
    username: string;
    role: 'admin' | 'user';
    email?: string;
    pointsBalance?: number;
  } | null;
};

export type UserInfo = {
  id: number;
  username: string;
  role: string;
  email?: string;
  isActive: boolean;
  pointsBalance?: number;
  createdAt?: string;
};

export const authApi = {
  async getStatus(): Promise<AuthStatusResponse> {
    const { data } = await apiClient.get<AuthStatusResponse>('/api/v1/auth/status');
    return data;
  },

  async login(username: string, password: string, passwordConfirm?: string): Promise<void> {
    const body: { username: string; password: string; passwordConfirm?: string } = { username, password };
    if (passwordConfirm !== undefined) {
      body.passwordConfirm = passwordConfirm;
    }
    await apiClient.post('/api/v1/auth/login', body);
  },

  async register(username: string, password: string, passwordConfirm: string): Promise<void> {
    await apiClient.post('/api/v1/auth/register', {
      username,
      password,
      passwordConfirm,
    });
  },

  async changePassword(
    currentPassword: string,
    newPassword: string,
    newPasswordConfirm: string
  ): Promise<void> {
    await apiClient.post('/api/v1/auth/change-password', {
      currentPassword,
      newPassword,
      newPasswordConfirm,
    });
  },

  async logout(): Promise<void> {
    await apiClient.post('/api/v1/auth/logout');
  },

  async updateSettings(
    authEnabled: boolean,
    password?: string,
    passwordConfirm?: string,
    currentPassword?: string
  ): Promise<AuthStatusResponse> {
    const body: {
      authEnabled: boolean;
      password?: string;
      passwordConfirm?: string;
      currentPassword?: string;
    } = { authEnabled };
    if (password !== undefined) body.password = password;
    if (passwordConfirm !== undefined) body.passwordConfirm = passwordConfirm;
    if (currentPassword !== undefined) body.currentPassword = currentPassword;
    const { data } = await apiClient.post<AuthStatusResponse>('/api/v1/auth/settings', body);
    return data;
  },

  // Admin user management
  async listUsers(): Promise<{ users: UserInfo[] }> {
    const { data } = await apiClient.get<{ users: UserInfo[] }>('/api/v1/auth/users');
    return data;
  },

  async createUser(
    username: string,
    password: string,
    passwordConfirm: string,
    role: string = 'user',
    email?: string
  ): Promise<{ ok: boolean; user: { id: number; username: string; role: string } }> {
    const { data } = await apiClient.post('/api/v1/auth/users', {
      username,
      password,
      passwordConfirm,
      role,
      email,
    });
    return data;
  },

  async updateUser(
    userId: number,
    updates: {
      role?: string;
      email?: string;
      isActive?: boolean;
      password?: string;
      passwordConfirm?: string;
      pointsBalance?: number;
    }
  ): Promise<{ ok: boolean }> {
    const { data } = await apiClient.put(`/api/v1/auth/users/${userId}`, updates);
    return data;
  },

  async deleteUser(userId: number): Promise<{ ok: boolean }> {
    const { data } = await apiClient.delete(`/api/v1/auth/users/${userId}`);
    return data;
  },

  async resetUserPassword(
    userId: number,
    newPassword: string,
    newPasswordConfirm: string
  ): Promise<{ ok: boolean }> {
    const { data } = await apiClient.post(`/api/v1/auth/users/${userId}/reset-password`, {
      newPassword,
      newPasswordConfirm,
    });
    return data;
  },

  async setUserPoints(
    userId: number,
    balance: number,
    reason?: string
  ): Promise<{ ok: boolean; balance: number }> {
    const { data } = await apiClient.post(`/api/v1/auth/users/${userId}/points`, {
      balance,
      reason,
    });
    return data;
  },
};
