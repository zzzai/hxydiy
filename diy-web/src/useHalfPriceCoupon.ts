import { useEffect, useState } from 'react';
import { getMyCoupons, type MyCoupon } from './api';
import { availableHalfPriceCoupon } from './halfPriceCoupon';

export function useHalfPriceCoupon(token: string | undefined, storeId: number): boolean {
  const [snapshot, setSnapshot] = useState<{ token: string; storeId: number; coupons: MyCoupon[] } | null>(null);
  useEffect(() => {
    setSnapshot(null);
    if (!token) return;
    let disposed = false;
    let version = 0;
    let expiresTimer: number | undefined;
    const refresh = async () => {
      const requestVersion = ++version;
      try {
        const coupons = await getMyCoupons(token);
        if (disposed || requestVersion !== version) return;
        window.clearTimeout(expiresTimer);
        setSnapshot({ token, storeId, coupons });
        const expiry = availableHalfPriceCoupon(coupons, storeId)?.expire_at;
        if (expiry) expiresTimer = window.setTimeout(() => { setSnapshot(null); void refresh(); }, Math.min(2147483647, Math.max(1, Date.parse(expiry) - Date.now())));
      } catch {
        if (!disposed && requestVersion === version) setSnapshot(null);
      }
    };
    const refreshVisible = () => { if (document.visibilityState === 'visible') void refresh(); };
    void refresh();
    const timer = window.setInterval(refreshVisible, 60000);
    window.addEventListener('focus', refreshVisible);
    document.addEventListener('visibilitychange', refreshVisible);
    return () => {
      disposed = true; version++;
      window.clearInterval(timer); window.clearTimeout(expiresTimer);
      window.removeEventListener('focus', refreshVisible);
      document.removeEventListener('visibilitychange', refreshVisible);
    };
  }, [token, storeId]);
  return Boolean(token && snapshot?.token === token && snapshot.storeId === storeId
    && availableHalfPriceCoupon(snapshot.coupons, storeId));
}
