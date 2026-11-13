export function formatMoney(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) return '—';
  const yuan = cents / 100;
  return `¥${Number.isInteger(yuan) ? yuan.toFixed(0) : yuan.toFixed(2)}`;
}

export function percentOffLabel(percentOff: number | null | undefined): string {
  if (!Number.isInteger(percentOff) || (percentOff as number) < 1 || (percentOff as number) > 100) return '比例缺失';
  const discount = (100 - (percentOff as number)) / 10;
  return `${Number.isInteger(discount) ? discount.toFixed(0) : discount.toFixed(1)}折`;
}

export function couponDiscountLabel(coupon: { coupon_type?: string | null; amount_cents?: number | null; percent_off?: number | null }): string {
  if (coupon.coupon_type === 'percent') return percentOffLabel(coupon.percent_off);
  return formatMoney(coupon.amount_cents);
}

export function budgetLabel(budgetCents: number | null | undefined): string {
  if (budgetCents === null || budgetCents === undefined) return '不限预算';
  if (budgetCents === 0) return '零预算';
  return formatMoney(budgetCents);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const normalized = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false });
}
