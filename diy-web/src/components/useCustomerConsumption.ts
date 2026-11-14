import { useEffect, useRef, useState } from 'react';

import { getMyMembershipConsumption, type CustomerConsumptionOverview } from '../api';
import { authFailureAction } from '../customerAuth';

type Loader = (token: string) => Promise<CustomerConsumptionOverview>;
type Entry = { token: string; data: CustomerConsumptionOverview | null; loading: boolean; error: string };

export function useCustomerConsumption(
  open: boolean,
  token: string | null,
  onAuthFailure: () => void,
  load: Loader = getMyMembershipConsumption,
  refreshKey = 0,
) {
  const [entry, setEntry] = useState<Entry | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const request = useRef(0);
  const context = useRef({ open, token });
  context.current = { open, token };
  const authFailure = useRef(onAuthFailure);
  authFailure.current = onAuthFailure;

  useEffect(() => {
    if (!open || !token) { setEntry(null); return; }
    const current = ++request.current;
    const activeToken = token;
    setEntry({ token: activeToken, data: null, loading: true, error: '' });
    const isCurrent = () => current === request.current && context.current.open && context.current.token === activeToken;
    load(activeToken)
      .then((result) => {
        if (!isCurrent()) return;
        setEntry({ token: activeToken, data: result, loading: false, error: '' });
      })
      .catch((reason) => {
        if (!isCurrent()) return;
        if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
          setEntry(null);
          authFailure.current();
          return;
        }
        setEntry({
          token: activeToken, data: null, loading: false,
          error: reason instanceof TypeError ? '消费记录暂时无法加载，请检查网络后重试。' : reason instanceof Error ? reason.message : '消费记录暂时无法加载',
        });
      });
    return () => { request.current += 1; };
  }, [open, token, load, refreshKey, retryKey]);

  const retry = () => setRetryKey(value => value + 1);
  if (!open || !token) return { data: null, loading: false, error: '', retry };
  const current = entry?.token === token ? entry : null;
  return {
    data: current?.data ?? null,
    loading: current ? current.loading : true,
    error: current?.error ?? '',
    retry,
  };
}
