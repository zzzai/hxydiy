import type { Project } from './domain';

const SELECTION_REASONS: Record<string, string> = {
  'hxy-qiqing-30': '想泡泡脚、喝杯热茶，不需要套餐按摩时，可以从这一项开始。',
  'hxy-xiangxiang-60': '想泡脚，也想多照顾手臂和足底，可以选这一项。',
  'hxy-xiaoqi-90': '不只照顾双脚，还想安排全身按摩，选这套更完整。',
  'hxy-nvshen-60': '想把双脚从泡脚到足膜、润足都照顾一下，可以选这套足护。',
  'hxy-tuina-70': '想安排全身推拿，再搭配艾灸，可以看看这套组合。',
  'hxy-spa-60': '想体验精油护理和草本热敷，可以选这套60分钟组合。',
  'hxy-spa-90': '想给精油护理留出更长时间，可以选这套90分钟组合。',
  'hxy-head-30': '只想安排头面耳按摩，不用选整套全身项目。',
  'hxy-foot-refine-1': '想做足部清洁与修整，可以先向前台说明需要处理的位置。',
  'hxy-oil-back-30': '只想照顾背部，可以选这项30分钟精油按摩。',
  'hxy-caier-30': '想单独安排耳部清洁与按摩，可以选这一项。',
  'hxy-cupping-scraping-1': '拔罐、刮痧选一项即可，服务前与技师确认部位。',
  'hxy-jubu-30': '只想多按一两个部位，可以按需要选择，不必选整套全身项目。',
  'hxy-taoke-60': '想分多次安排护理，可以先了解这套10次服务的内容和使用方式。',
};

export function projectSelectionReason(code: string): string | undefined {
  return SELECTION_REASONS[code];
}

export function packageSessionExplanation(project: Project, totalCents: number): { count: number; average: string } | null {
  const match = project.price_label?.match(/^(\d+)次\/套$/);
  const count = match ? Number(match[1]) : 0;
  if (!Number.isSafeInteger(count) || count <= 0 || !Number.isSafeInteger(totalCents) || totalCents <= 0) return null;
  return { count, average: new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(totalCents / 100 / count) };
}
