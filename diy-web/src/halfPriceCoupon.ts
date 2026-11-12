import type { MyCoupon } from './api.ts';
import type { Project } from './domain.ts';

export function availableHalfPriceCoupon(coupons: MyCoupon[], storeId: number, now = Date.now()): MyCoupon | null {
  return coupons.find(coupon => coupon.store_id === storeId && coupon.usage_scope === 'foot_spa_main'
    && coupon.coupon_type === 'percent' && coupon.percent_off === 50 && coupon.min_spend_cents === 0
    && coupon.status === 'unused' && coupon.expire_at != null && Date.parse(coupon.expire_at) > now) || null;
}

export function halfPriceForProject(project: Project, hasCoupon: boolean): number | null {
  const price = project.half_price_coupon_price_cents;
  return hasCoupon && typeof price === 'number' && Number.isInteger(price) && price > 0 ? price : null;
}
