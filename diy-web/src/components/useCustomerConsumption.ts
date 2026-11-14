import { useEffect, useRef, useState } from 'react';

import { getMyMembershipConsumption, type CustomerConsumptionOverview } from '../api';
import { authFailureAction } from '../customerAuth';

type Loader = (token: string, offset: number, limit: number) => Promise<CustomerConsumptionOverview>;
type Entry = {
  token: string;
  data: CustomerConsumptionOverview | null;
  bills: CustomerConsumptionOverview['bills'];
  loading: boolean;
  loadingMore: boolean;
  error: string;
};

const PAGE_SIZE = 20;

function describeError(reason: unknown): string {
  if (reason instanceof TypeError) return '消费记录暂时无法加载，请检查网络后重试。';
  return reason instanceof Error ? reason.message : '消费记录暂时无法加载';
}

function mergeBills(existing: CustomerConsumptionOverview['bills'], incoming: CustomerConsumptionOverview['bills']) {
  const seen = new Set(existing.map((bill) => bill.id));
  const merged = [...existing];
  for (const bill of incoming) {
    if (seen.has(bill.id)) continue;
    seen.add(bill.id);
    merged.push(bill);
  }
  return merged;
}

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
  const loadingMoreRef = useRef(false);
  const context = useRef({ open, token });
  context.current = { open, token };
  const authFailure = useRef(onAuthFailure);
  authFailure.current = onAuthFailure;

  useEffect(() => {
    if (!open || !token) { setEntry(null); loadingMoreRef.current = false; return; }
    const current = ++request.current;
    loadingMoreRef.current = false;
    const activeToken = token;
    setEntry({ token: activeToken, data: null, bills: [], loading: true, loadingMore: false, error: '' });
    const isCurrent = () => current === request.current && context.current.open && context.current.token === activeToken;
    load(activeToken, 0, PAGE_SIZE)
      .then((result) => {
        if (!isCurrent()) return;
        setEntry({ token: activeToken, data: result, bills: result.bills, loading: false, loadingMore: false, error: '' });
      })
      .catch((reason) => {
        if (!isCurrent()) return;
        if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
          setEntry(null);
          authFailure.current();
          return;
        }
        setEntry({ token: activeToken, data: null, bills: [], loading: false, loadingMore: false, error: describeError(reason) });
      });
    return () => { request.current += 1; };
  }, [open, token, load, refreshKey, retryKey]);

  const loadMore = () => {
    if (!open || !token || !entry || entry.token !== token || entry.loading || entry.loadingMore) return;
    if (loadingMoreRef.current) return;  // synchronous in-flight guard
    const activeToken = token;
    const current = request.current;
    // Advance the server offset independently of the unique rendered count.
    const nextOffset = entry.data ? entry.data.pagination.offset + entry.data.pagination.limit : entry.bills.length;
    loadingMoreRef.current = true;
    setEntry({ ...entry, loadingMore: true, error: '' });
    load(activeToken, nextOffset, PAGE_SIZE)
      .then((result) => {
        if (current !== request.current || !context.current.open || context.current.token !== activeToken) return;
        loadingMoreRef.current = false;
        setEntry(prev => prev && prev.token === activeToken ? {
          ...prev, data: result, bills: mergeBills(prev.bills, result.bills), loading: false, loadingMore: false, error: '',
        } : prev);
      })
      .catch((reason) => {
        if (current !== request.current || !context.current.open || context.current.token !== activeToken) return;
        loadingMoreRef.current = false;
        if (['reauthenticate', 'session-replaced'].includes(authFailureAction(reason))) {
          setEntry(null);
          authFailure.current();
          return;
        }
        setEntry(prev => prev && prev.token === activeToken ? { ...prev, loadingMore: false, error: describeError(reason) } : prev);
      });
  };

  const retry = () => setRetryKey(value => value + 1);
  if (!open || !token) return { data: null, bills: [], loading: false, loadingMore: false, hasMore: false, error: '', retry, loadMore };
  const current = entry?.token === token ? entry : null;
  return {
    data: current?.data ?? null,
    bills: current?.bills ?? [],
    loading: current ? current.loading : true,
    loadingMore: current ? current.loadingMore : false,
    hasMore: current?.data ? current.data.pagination.has_more : false,
    error: current?.error ?? '',
    retry,
    loadMore,
  };
}
