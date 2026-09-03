import type { Addon } from './domain.ts';

export type FallbackOptionGroup = { label: string; note: string; options: string[] };

const FALLBACK_GROUPS: Record<string, FallbackOptionGroup[]> = {
  'hxy-qiqing-30': [
    { label: '泡脚液', note: '请选择一项 · 不加价', options: ['门店推荐', '清新草木香', '暖香草本'] },
    { label: '手法力度', note: '请选择一项 · 不加价', options: ['轻缓', '适中', '有力'] },
  ],
  'hxy-xiangxiang-60': [
    { label: '泡脚液', note: '请选择一项 · 不加价', options: ['经典草本方', '姜艾暖足方', '陈皮舒缓方'] },
    { label: '手法力度', note: '请选择一项 · 不加价', options: ['轻缓', '适中', '有力'] },
    { label: '细节护理', note: '请选择一项 · 不加价', options: ['修脚', '搓盐'] },
  ],
  'hxy-xiaoqi-90': [
    { label: '泡脚液', note: '请选择一项 · 不加价', options: ['经典草本方', '姜艾暖足方', '陈皮舒缓方'] },
    { label: '手法力度', note: '请选择一项 · 不加价', options: ['轻缓', '适中', '有力'] },
    { label: '重点调理', note: '请选择一项 · 不加价', options: ['腰肾调理', '肠胃调理'] },
  ],
  'hxy-tuina-70': [
    { label: '手法力度', note: '请选择一项 · 不加价', options: ['轻缓', '适中', '有力'] },
  ],
  'hxy-spa-90': [
    { label: '精油', note: '请选择一项 · 不加价', options: ['清润草木', '温暖木质', '舒缓花香'] },
    { label: '手法力度', note: '请选择一项 · 不加价', options: ['轻缓', '适中', '有力'] },
  ],
  'hxy-spa-60': [
    { label: '精油', note: '请选择一项 · 不加价', options: ['清润草木', '温暖木质', '舒缓花香'] },
    { label: '手法力度', note: '请选择一项 · 不加价', options: ['轻缓', '适中', '有力'] },
  ],
};

function groupIdentity(label: string): string {
  const normalized = label.normalize('NFKC').trim();
  if (normalized.includes('精油')) return '精油';
  if (normalized.includes('力度')) return '手法力度';
  if (normalized.includes('草本') || normalized === '泡脚液') return '泡脚液';
  return normalized;
}

export function fallbackOptionGroups(code: string): FallbackOptionGroup[] {
  return (FALLBACK_GROUPS[code] || []).map((group) => ({ ...group, options: [...group.options] }));
}

export function withFallbackOptionGroups(configured: FallbackOptionGroup[], code: string): FallbackOptionGroup[] {
  const existing = new Set(configured.map((group) => groupIdentity(group.label)));
  return [
    ...configured,
    ...fallbackOptionGroups(code).filter((group) => !existing.has(groupIdentity(group.label))),
  ];
}

export function fallbackAttachableAddons(addons: Addon[], projectId: number): Addon[] {
  return addons.filter((addon) => (
    addon.can_attach_to_parent
    && (addon.parent_project_id === null || addon.parent_project_id === projectId)
  ));
}
