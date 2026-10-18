import assert from 'node:assert/strict';
import test from 'node:test';
import axios, { AxiosError } from 'axios';
import { installSessionGuards } from '../src/apiSession.ts';
import { clearStaffSession, commitStaffSession, getSessionEpoch, isStaleSessionError } from '../src/wecomSession.ts';
const values = new Map<string, string>();
const storage = { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => values.set(k, v), removeItem: (k: string) => values.delete(k) };
Object.assign(globalThis, { localStorage: storage, sessionStorage: storage });
const session = (n: number) => ({ token: 'synthetic-' + n, staff: { id: n } });
for (const status of [200, 401]) {
  test('late ' + status + ' cannot escape the old session or trigger current error handler', async () => {
    clearStaffSession(); commitStaffSession(session(1), getSessionEpoch());
    let settle!: () => void;
    const client = axios.create({ adapter: (config) => new Promise((resolve, reject) => {
      settle = () => {
        const response = { config, data: { customer_name: 'old identity' }, status, statusText: '', headers: {} };
        if (status === 401) reject(new AxiosError('unauthorized', 'ERR_BAD_RESPONSE', config, undefined, response));
        else resolve(response);
      };
    }) });
    installSessionGuards(client);
    let currentErrors = 0;
    client.interceptors.response.use(undefined, (error) => {
      if (!isStaleSessionError(error)) currentErrors++;
      return Promise.reject(error);
    });
    const request = client.get('/synthetic-sensitive-data');
    commitStaffSession(session(2), getSessionEpoch()); settle();
    await assert.rejects(request, isStaleSessionError);
    assert.equal(currentErrors, 0);
    assert.equal(storage.getItem('hxy_admin_token'), 'synthetic-2');
  });
}
test('current responses remain available and current 401 still reaches ordinary handler', async () => {
  clearStaffSession();
  const client = axios.create({ adapter: async (config) => ({ config, status: 200, data: { ok: true }, statusText: '', headers: {} }) });
  installSessionGuards(client);
  assert.deepEqual((await client.get('/ok')).data, { ok: true });
  let currentErrors = 0;
  client.interceptors.response.use(undefined, (error) => {
    if (!isStaleSessionError(error)) currentErrors++;
    return Promise.reject(error);
  });
  client.defaults.adapter = async (config) => {
    throw new AxiosError('unauthorized', 'ERR_BAD_RESPONSE', config, undefined,
      { config, status: 401, data: {}, statusText: '', headers: {} });
  };
  await assert.rejects(client.get('/unauthorized'), (error: unknown) => axios.isAxiosError(error) && error.response?.status === 401);
  assert.equal(currentErrors, 1);
});
