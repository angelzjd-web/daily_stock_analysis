import apiClient from './index';

export type PointsBalanceResponse = {
  balance: number;
  insufficient: boolean;
};

export type PointTransaction = {
  id: number;
  change: number;
  balanceAfter: number;
  type: string;
  description: string | null;
  createdAt: string | null;
};

export type PointsTransactionsResponse = {
  transactions: PointTransaction[];
};

export const pointsApi = {
  async getBalance(): Promise<PointsBalanceResponse> {
    const { data } = await apiClient.get<PointsBalanceResponse>('/api/v1/points/balance');
    return data;
  },

  async getTransactions(limit: number = 20): Promise<PointsTransactionsResponse> {
    const { data } = await apiClient.get<PointsTransactionsResponse>('/api/v1/points/transactions', {
      params: { limit },
    });
    return data;
  },
};
