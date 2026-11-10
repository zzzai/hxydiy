import { ApiError, bindGuestCoupon } from './api';

export const GUEST_COUPON_KEY_PREFIX = 'hxy_coupon_guest_';

/** Bind every anonymous coupon issued from a manager link to the account that just logged in. */
export async function bindPendingGuestCoupons(authToken: string): Promise<void> {
  if (!authToken) return;
  const keys: string[] = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (key?.startsWith(GUEST_COUPON_KEY_PREFIX)) keys.push(key);
  }
  for (const key of keys) {
    const token = window.localStorage.getItem(key);
    if (!token) continue;
    try {
      await bindGuestCoupon(token, authToken);
      window.localStorage.removeItem(key);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === 'COUPON_ALREADY_BOUND') {
        window.localStorage.removeItem(key);
      }
      // A coupon already held by this account is shown from /coupons instead.
    }
  }
}
