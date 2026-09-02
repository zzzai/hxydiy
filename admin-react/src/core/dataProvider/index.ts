import type { AxiosRequestConfig, AxiosResponse } from 'axios';
import { client } from '../../api.ts';
import { clearAuthSession, redirectToLogin } from '../auth/index.ts';
import { withBoundStore } from '../auth/storeContext.ts';
import { DataProviderError, normalizeProviderError } from './errors.ts';
import { buildQueryKey, resourceQueryKey, type QueryParams } from './queryKeys.ts';

export { DataProviderError } from './errors.ts';
export { buildQueryKey, resourceQueryKey } from './queryKeys.ts';

type Identifier = number | string;
type Request = <T = unknown>(config: AxiosRequestConfig) => Promise<AxiosResponse<T>>;

class AdminDataProvider {
  request: Request = (config) => client.request(config);
  private storeId: number | null = null;
  private readonly cache = new Map<string, unknown>();

  setStoreId(storeId: number | null | undefined) {
    this.storeId = storeId || null;
    this.cache.clear();
  }
  getQueryKey(resource: string, params: QueryParams = {}) { return buildQueryKey(resource, params); }
  invalidate(resource: string, id?: Identifier) {
    const prefix = id === undefined ? `${resource}:` : resourceQueryKey(resource, id);
    for (const key of this.cache.keys()) if (key.startsWith(prefix)) this.cache.delete(key);
  }

  async getList<T>(resource: string, params: QueryParams = {}): Promise<T> {
    const key = buildQueryKey(resource, params);
    if (this.cache.has(key)) return this.cache.get(key) as T;
    const result = await this.execute<T>({ method: 'GET', url: resource, params });
    this.cache.set(key, result);
    return result;
  }

  async getOne<T>(resource: string, id: Identifier): Promise<T> {
    const key = resourceQueryKey(resource, id);
    if (this.cache.has(key)) return this.cache.get(key) as T;
    const result = await this.execute<T>({ method: 'GET', url: `${resource}/${id}` });
    this.cache.set(key, result);
    return result;
  }

  async create<TInput extends Record<string, unknown>, T>(resource: string, input: TInput, idempotencyKey?: string): Promise<T> {
    const result = await this.execute<T>({ method: 'POST', url: resource, data: withBoundStore(input, this.storeId), headers: idempotencyKey ? { 'X-Idempotency-Key': idempotencyKey } : undefined });
    this.invalidate(resource);
    return result;
  }

  async update<TInput extends Record<string, unknown>, T>(resource: string, id: Identifier, input: TInput, version?: number): Promise<T> {
    // PATCH 负载默认保持资源契约；只有调用方显式带 store_id 时才校正门店归属。
    const data = Object.prototype.hasOwnProperty.call(input, 'store_id') ? withBoundStore(input, this.storeId) : input;
    const result = await this.execute<T>({ method: 'PATCH', url: `${resource}/${id}`, data, headers: version === undefined ? undefined : { 'If-Match': String(version) } });
    this.invalidate(resource);
    return result;
  }

  async remove<T>(resource: string, id: Identifier): Promise<T> {
    const result = await this.execute<T>({ method: 'DELETE', url: `${resource}/${id}` });
    this.invalidate(resource);
    return result;
  }

  private async execute<T>(config: AxiosRequestConfig): Promise<T> {
    try { return (await this.request<T>(config)).data; }
    catch (error) {
      const normalized = normalizeProviderError(error);
      if (normalized.status === 401 && typeof window !== 'undefined') { clearAuthSession(); redirectToLogin(); }
      throw normalized;
    }
  }
}

export const dataProvider = new AdminDataProvider();
