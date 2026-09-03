import { formatMoney, type PricingPreview } from './domain.ts';

export const FEEDBACK_TAGS = ['技术专业', '环境舒适', '技师细致', '力度合适', '整体放松'] as const;

const PREFERENCE_LABELS: Record<string, string> = {
  草本偏好: '泡脚液',
  草本配方: '泡脚液',
  力度偏好: '手法力度',
  力度: '手法力度',
  服务侧重: '放松重点',
};

export function customerPreferenceLabel(label: string): string {
  const normalized = label.normalize('NFKC').trim();
  return PREFERENCE_LABELS[normalized] || normalized;
}

export function customerPreferenceNote(note: string): string {
  const normalized = note.normalize('NFKC').trim();
  if (['到店确认', '按偏好', '任选一项'].includes(normalized)) return '请选择一项 · 不加价';
  if (normalized === '到店沟通') return '按偏好选择 · 不加价';
  return normalized || '请选择一项 · 不加价';
}

export function customerPageSubtitle(subtitle: string | null | undefined): string {
  const normalized = (subtitle || '').normalize('NFKC').trim();
  return /^按需要[,，]自由搭配$/.test(normalized) ? '到店先一杯' : normalized || '到店先一杯';
}

function normalizedParts(parts: string[]): string[] {
  return [...new Set(parts.map((part) => part.normalize('NFKC').trim()).filter(Boolean))];
}

export function customerOptionDescription(
  description: string | null | undefined,
  durationMin: number,
): string {
  const cleaned = (description || '')
    .replace(/到店确认部位|到店确认/g, '')
    .replace(/^[\s·｜|,，、;；:：-]+|[\s·｜|,，、;；:：-]+$/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
  if (!cleaned) return `约${durationMin}分钟`;
  if (/^\d+分钟$/.test(cleaned)) return `约${cleaned}`;
  return cleaned;
}

export function preferenceSummary(groupNames: string[]): string {
  const names = groupNames.map((name) => name.trim()).filter(Boolean);
  if (names.length === 0) return '请选择服务偏好，均不加价';
  if (names.length === 1) return `请选择${names[0]}，不加价`;
  if (names.length === 2) return `请选择${names[0]}和${names[1]}，均不加价`;
  return `请选择${names.slice(0, -1).join('、')}和${names.at(-1)}，均不加价`;
}

export function footBathBundleCopy(
  preview: PricingPreview,
  selectedParts: string[],
  isMember: boolean,
): { title: string; detail: string; value: string } {
  const count = Math.min(normalizedParts(selectedParts).length, 2);
  if (preview.qualified) {
    const adjustment = isMember ? preview.memberAdjustmentCents : preview.storeAdjustmentCents;
    return {
      title: '已免基础泡脚费',
      detail: '已选2个不同部位',
      value: `-${formatMoney(Math.abs(adjustment))}`,
    };
  }
  return {
    title: count === 1 ? '再选1个不同部位，基础泡脚费可免' : '选2个不同部位，基础泡脚费可免',
    detail: '局部加强按所选部位计费',
    value: `${count}/2`,
  };
}

export function selectionSettlementNote(readOnly: boolean): string {
  return readOnly
    ? '已由门店确认，以门店最终清单为准'
    : '服务完成后统一线下结算，最终以门店确认的服务清单为准';
}

export function projectDetailActionLabel(
  selected: boolean,
  readOnly: boolean,
  hasErrors: boolean,
): string {
  if (readOnly) return '已提交前台';
  if (hasErrors) return '请先选完服务偏好';
  return selected ? '保存本次选择' : '加入本次服务';
}

export function shouldShowCouponPrompt(isMember: boolean, detailOnly: boolean): boolean {
  return !isMember && !detailOnly;
}

export function shouldShowCouponTab(isMember: boolean): boolean {
  return !isMember;
}

export function shouldShowMembershipPromos(isMember: boolean): boolean {
  return !isMember;
}

export function selectionPriceDisplay(
  isMember: boolean,
  payableCents: number,
  memberCents: number | null | undefined,
  storeCents: number | null | undefined,
): {
  primaryLabel: '门店价' | '会员价';
  memberHint: string | null;
  savingCents: number;
  originalHint: string | null;
  realizedSavingCents: number;
} {
  const member = Number(memberCents);
  const store = Number(storeCents);
  const hasMemberSaving = !isMember && Number.isFinite(member) && member >= 0 && member < payableCents;
  const realizedSaving = isMember && Number.isFinite(store) && store > payableCents ? store - payableCents : 0;
  return {
    primaryLabel: isMember ? '会员价' : '门店价',
    memberHint: hasMemberSaving ? `会员价 ${formatMoney(member)}` : null,
    savingCents: hasMemberSaving ? payableCents - member : 0,
    originalHint: realizedSaving > 0 ? `门店价 ${formatMoney(store)}` : null,
    realizedSavingCents: realizedSaving,
  };
}

export function serviceFeedbackAction(canEvaluate: boolean, evaluated: boolean): '评价本次服务' | '已完成评价' | null {
  if (evaluated) return '已完成评价';
  return canEvaluate ? '评价本次服务' : null;
}

export function customerLoginCopy(kind: 'profile' | 'record'): {
  title: string;
  detail: string;
  action: string;
} {
  return kind === 'profile'
    ? {
      title: '登录后，服务记录随时可查',
      detail: '查看本次清单、服务进度和评价，优惠券也会跟着账号走。',
      action: '登录查看记录',
    }
    : {
      title: '登录后，本次服务记录不丢',
      detail: '可随时查看本次清单、服务进度和评价。',
      action: '登录并查看记录',
    };
}
