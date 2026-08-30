export type ProviderErrorCode = 'UNAUTHORIZED' | 'FORBIDDEN' | 'CONFLICT' | 'REQUEST_FAILED';

export class DataProviderError extends Error {
  readonly status: number;
  readonly code: ProviderErrorCode;
  readonly detail?: unknown;
  constructor(status: number, code: ProviderErrorCode, message: string, detail?: unknown) {
    super(message);
    this.name = 'DataProviderError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export function normalizeProviderError(error: any): DataProviderError {
  const status = Number(error?.response?.status || 0);
  const detail = error?.response?.data?.detail;
  const message = typeof detail === 'string' ? detail : detail?.message || '请求失败';
  const code: ProviderErrorCode = status === 401 ? 'UNAUTHORIZED'
    : status === 403 ? 'FORBIDDEN'
      : status === 409 ? 'CONFLICT' : 'REQUEST_FAILED';
  return new DataProviderError(status, code, message, detail);
}
