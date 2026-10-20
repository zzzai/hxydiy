import type { AxiosInstance, AxiosRequestConfig } from 'axios';
import { getSessionEpoch, StaleSessionError } from './wecomSession.ts';
import { readActiveToken } from './staffSession.ts';

type ScopedConfig = AxiosRequestConfig & { hxySession?: { epoch: number; token: string | null } };
function assertCurrent(config?: ScopedConfig): void {
  const snapshot = config?.hxySession;
  if (snapshot && (snapshot.epoch !== getSessionEpoch() || snapshot.token !== readActiveToken(localStorage))) {
    throw new StaleSessionError();
  }
}
export function installSessionGuards(client: AxiosInstance): void {
  client.interceptors.request.use((config) => {
    (config as ScopedConfig).hxySession = { epoch: getSessionEpoch(), token: readActiveToken(localStorage) };
    return config;
  }, undefined, { synchronous: true });
  client.interceptors.response.use((response) => {
    assertCurrent(response.config);
    return response;
  }, (error) => {
    assertCurrent(error.config);
    return Promise.reject(error);
  });
}
