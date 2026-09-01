export type SavingHint = {
  kind: 'member' | 'coupon';
  estimated_saving_cents?: number;
  login_required: boolean;
};

export function selectSavingHint(member: SavingHint | null, coupon: SavingHint | null): SavingHint | null {
  if (member?.kind === 'member' && (member.estimated_saving_cents || 0) > 0) return member;
  // 会员差价为零或缺失时不提示会员；券引导不承诺金额，只在存在时展示。
  return coupon;
}
