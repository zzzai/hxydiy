import type { AxiosInstance, AxiosRequestConfig } from 'axios';
import { getSessionEpoch, StaleSessionError } from './wecomSession.ts';

type ScopedConfig = AxiosRequestConfig & { hxySession?: { epoch: number; token: string | null } };
function assertCurrent(config?: ScopedConfig): void {
  const snapshot = config?.hxySession;
  if (snapshot && (snapshot.epoch !== getSessionEpoch() || snapshot.token !== localStorage.getItem('hxy_admin_token'))) {
    throw new StaleSessionError();
  }
}
export function installSessionGuards(client: AxiosInstance): void {
  client.interceptors.request.use((config) => {
    (config as ScopedConfig).hxySession = { epoch: getSessionEpoch(), token: localStorage.getItem('hxy_admin_token') };
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
