import type { CatalogOptionGroup, ProjectCatalogSelection } from './catalogOptions.ts';

export type Price = {
  price_type: 'store' | 'group' | 'member' | string;
  amount_cents: number;
};

export type Project = {
  id: number;
  code: string;
  category: string;
  category_mark: string;
  name: string;
  duration_min: number | null;
  summary: string;
  image_url: string;
  tags: string[];
  detail_modules?: Array<{ type?: string; title?: string; body?: string; image_url?: string }>;
  diy_options?: Array<{ label: string; note?: string; options?: string[] }>;
  display_order?: number;
  price_label: string;
  prices: Price[];
  catalog_version_id?: number | null;
  catalog_version?: number | null;
  option_groups?: CatalogOptionGroup[];
};

export type Addon = {
  id: number;
  code: string;
  name: string;
  parent_project_id: number | null;
  duration_min: number | null;
  summary: string;
  image_url: string;
  display_order: number;
  chargeable: boolean;
  independently_sellable: boolean;
  can_attach_to_parent: boolean;
  prices: { store: number; member: number };
};

export type SelectionItem = {
  project_id: number | string;
  catalog_version_id?: number;
  option_choice_ids?: number[];
  quantity: number;
  addon_ids: number[];
  diy_preferences: string[];
  item_type: 'service' | 'preference';
  chargeable: boolean;
};

export type BuildSelectionInput = {
  projects: Project[];
  selectedProjectIds: number[];
  projectAddonIds?: Record<number, number[]>;
  addons?: Addon[];
  projectPreferences?: Record<number, string[]>;
  projectCatalogSelections?: Record<number, ProjectCatalogSelection>;
  localParts: string[];
  tea: string | null;
};

export type PricingPreview = {
  storeSubtotalCents: number;
  memberSubtotalCents: number;
  storeAdjustmentCents: number;
  memberAdjustmentCents: number;
  storeTotalCents: number;
  memberTotalCents: number;
  qualified: boolean;
};

export function emptyPricingPreview(): PricingPreview {
  return {
    storeSubtotalCents: 0,
    memberSubtotalCents: 0,
    storeAdjustmentCents: 0,
    memberAdjustmentCents: 0,
    storeTotalCents: 0,
    memberTotalCents: 0,
    qualified: false,
  };
}

export function displayPayableTotal(input: {
  readOnly: boolean;
  serverTotalCents: number | null;
  previewStoreTotalCents: number;
  previewMemberTotalCents: number;
  priceType: 'store' | 'member';
}): number {
  const previewTotal = input.priceType === 'member'
    ? input.previewMemberTotalCents
    : input.previewStoreTotalCents;
  return input.readOnly && input.serverTotalCents !== null && Number.isFinite(input.serverTotalCents)
    ? input.serverTotalCents
    : previewTotal;
}

/**
 * 读取已提交会话的会员整单金额。
 * 旧会话可能把单项金额写入 member_total_cents；无促销时以快照小计/明细行重算，
 * 避免顾客看到 67 元这类单项金额。存在促销时必须保留服务端最终减免后的总价。
 */
export function resolveMemberTotalCents(
  snapshot: Record<string, unknown> | null | undefined,
  fallbackCents: number | null | undefined,
): number {
  const data = snapshot || {};
  const promotionCode = String(data.promotion_code ?? '').trim();
  const snapshotTotal = Number(data.member_total_cents);
  const fallback = Number(fallbackCents);

  if (promotionCode) {
    if (Number.isFinite(snapshotTotal) && snapshotTotal >= 0) return snapshotTotal;
    if (Number.isFinite(fallback) && fallback >= 0) return fallback;
  }

  const subtotal = Number(data.member_subtotal_cents);
  if (Number.isFinite(subtotal) && subtotal >= 0) return subtotal;

  const lines = Array.isArray(data.lines) ? data.lines : [];
  const lineTotal = lines.reduce((sum, line) => {
    if (!line || typeof line !== 'object') return sum;
    const value = Number((line as Record<string, unknown>).member_line_total_cents);
    return Number.isFinite(value) && value >= 0 ? sum + value : sum;
  }, 0);
  if (lineTotal > 0) return lineTotal;
  if (Number.isFinite(snapshotTotal) && snapshotTotal >= 0) return snapshotTotal;
  return Number.isFinite(fallback) && fallback >= 0 ? fallback : 0;
}

export type CouponReminder = {
  name: string;
  amount_cents: number;
  min_spend_cents: number;
};

export function assetPath(fileName: string, baseUrl = import.meta.env?.BASE_URL ?? '/diy/'): string {
  const normalizedBase = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
  return `${normalizedBase}assets/${fileName.replace(/^\/+/, '')}`;
}

export const TEAS = [
  { name: '老姜茶', note: '辛香温润', image: assetPath('fresh-ginger.jpg') },
  { name: '陈皮茶', note: '清香顺口', image: assetPath('hxy-herbal-tea-cup.webp') },
  { name: '玫瑰茶', note: '柔和花香', image: assetPath('home-herbal-wellness-tea.webp') },
] as const;

export function resolveTeaImage(option: { name: string; image_url?: string; image?: string }): string {
  return option.image_url || option.image || TEAS.find((tea) => tea.name === option.name)?.image || TEAS[0].image;
}

export const TEA_SERVICE = {
  name: '五行茶饮',
  summary: '随到店项目提供，先喝一杯热茶，再慢慢进入放松状态。',
  image: assetPath('hxy-herbal-tea-cup.webp'),
  availability: 'preference',
} as const;

export const TEA_DETAIL_PROFILES: Record<(typeof TEAS)[number]['name'], { description: string; highlight: string }> = {
  老姜茶: { description: '姜香温润，适合偏爱浓郁暖香口感的顾客。', highlight: '辛香温润' },
  陈皮茶: { description: '陈皮清香，入口顺和，适合日常慢饮。', highlight: '清香顺口' },
  玫瑰茶: { description: '花香柔和，口感清雅，适合偏爱轻盈香气的顾客。', highlight: '柔和花香' },
};

export const LOCAL_PARTS = ['肩颈', '腰臀', '腿部', '腹部', '足部'] as const;
export const LOCAL_DETAIL_PROFILES: Record<(typeof LOCAL_PARTS)[number], { description: string; focus: string }> = {
  肩颈: { description: '围绕肩颈容易紧绷的区域进行日常放松。', focus: '肩颈舒缓' },
  腰臀: { description: '围绕腰背与臀部容易疲劳的区域进行日常放松。', focus: '腰臀放松' },
  腿部: { description: '围绕大腿与小腿的疲劳区域进行日常放松。', focus: '腿部舒缓' },
  腹部: { description: '以轻柔方式完成腹部日常放松，力度可按舒适程度调整。', focus: '轻柔放松' },
  足部: { description: '围绕足底与足踝区域进行日常放松。', focus: '足部放松' },
};

export const CATALOG_SECTIONS = [
  { id: 'tea', mark: '茶', label: '茶饮', categories: [] },
  { id: 'bath', mark: '泡', label: '泡脚沐足', categories: ['bath'] },
  { id: 'balance', mark: '调', label: '推拿', categories: ['balance'] },
  { id: 'care', mark: '补', label: '精油SPA', categories: ['care'] },
  { id: 'small', mark: '辅', label: '更多服务', categories: ['small', 'local-strength'] },
  { id: 'kit', mark: '养', label: '功夫套盒', categories: ['kit'] },
] as const;

export function displayProjectName(project: Pick<Project, 'code' | 'name'>): string {
  if (project.code === 'hxy-spa-60') return '60分钟精油SPA';
  if (project.code === 'hxy-spa-90') return '90分钟精油SPA';
  return project.name;
}

const FEATURED_CODES = ['hxy-qiqing-30', 'hxy-tuina-70', 'hxy-spa-90', 'hxy-taoke-60'] as const;

// 固定套盒：category 为 kit，或历史误分类但仍为套盒的稳定编码。
const DETAIL_ONLY_CODES = new Set(['hxy-taoke-60']);

export function catalogProjectsForSection(projects: Project[], sectionId: string): Project[] {
  const section = CATALOG_SECTIONS.find((item) => item.id === sectionId);
  if (!section) return [];
  return projects.filter((project) => section.categories.includes(project.category as never));
}

export function featuredProjects(projects: Project[]): Project[] {
  const byCode = new Map(projects.map((project) => [project.code, project]));
  return FEATURED_CODES.map((code) => byCode.get(code)).filter((project): project is Project => Boolean(project));
}

export function canCustomerChangePosition(source: string, positionType: string, occupancyStatus: string | undefined): boolean {
  return !['kiosk', 'personal_qr', 'room_qr'].includes(source) && positionType === 'sofa' && occupancyStatus === 'held';
}

export function requiresStaffKioskBinding(source: string, hasTrustedSession: boolean): boolean {
  return source === 'kiosk' && !hasTrustedSession;
}

export function shouldClearDeviceSessionAfterSubmit(source: string): boolean {
  return source === 'kiosk';
}

export const KIOSK_UNBOUND_COPY = {
  title: '共享 iPad 等待前台绑定',
  message: '本次顾客会话已结束，请交回工作人员重新生成顾客页面。',
} as const;

export function replaceTea(_current: string | null, next: string): string {
  return next;
}

export function priceOf(project: Project, priceType: 'store' | 'member'): number {
  const byType = new Map(project.prices.map((price) => [price.price_type, price.amount_cents]));
  if (priceType === 'member') {
    return byType.get('member') ?? byType.get('group') ?? byType.get('store') ?? 0;
  }
  return byType.get('store') ?? byType.get('group') ?? byType.get('member') ?? 0;
}

export function effectivePriceType(isMember: boolean): 'store' | 'member' {
  return isMember ? 'member' : 'store';
}

export function effectivePrice(project: Project, isMember: boolean): number {
  return priceOf(project, effectivePriceType(isMember));
}

export function addonPriceOf(addon: Addon, isMember: boolean): number {
  return isMember ? addon.prices.member : addon.prices.store;
}

export function effectivePriceLabel(isMember: boolean): '门店价' | '会员价' {
  return isMember ? '会员价' : '门店价';
}

export type PriceGuidance = {
  primaryLabel: '门店价' | '会员价';
  primaryCents: number;
  strikethroughCents: number | null;
  memberHintCents: number | null;
  hintText: string;
  hintAction: 'login' | 'card' | null;
};

export function priceGuidanceForPrices(
  store: number,
  member: number,
  auth: { is_member: boolean } | null,
): PriceGuidance {
  if (auth?.is_member) {
    return {
      primaryLabel: '会员价', primaryCents: member, strikethroughCents: store,
      memberHintCents: null, hintText: '', hintAction: null,
    };
  }
  if (!auth) {
    return {
      primaryLabel: '门店价', primaryCents: store, strikethroughCents: null,
      memberHintCents: member, hintText: `登录享会员价 ${formatMoney(member)}`, hintAction: 'login',
    };
  }
  return {
    primaryLabel: '门店价', primaryCents: store, strikethroughCents: null,
    memberHintCents: member, hintText: `办卡享会员价 ${formatMoney(member)}`, hintAction: 'card',
  };
}

/** 价格引导：未登录显示门店价+登录提示；非会员显示门店价+办卡提示；会员显示会员价。 */
export function priceGuidance(project: Project, auth: { is_member: boolean } | null): PriceGuidance {
  const store = priceOf(project, 'store');
  const member = priceOf(project, 'member');
  return priceGuidanceForPrices(store, member, auth);
}

export type ProjectListPricePresentation = {
  primaryCents: number;
  primaryPrefix: '' | '会员';
  secondaryCents: number;
  secondaryPrefix: '' | '会员';
  secondaryStrikethrough: boolean;
};

export function projectListPricePresentation(
  project: Project,
  auth: { is_member: boolean } | null,
): ProjectListPricePresentation {
  const storeCents = priceOf(project, 'store');
  const memberCents = priceOf(project, 'member');
  if (auth?.is_member) {
    return {
      primaryCents: memberCents,
      primaryPrefix: '会员',
      secondaryCents: storeCents,
      secondaryPrefix: '',
      secondaryStrikethrough: true,
    };
  }
  return {
    primaryCents: storeCents,
    primaryPrefix: '',
    secondaryCents: memberCents,
    secondaryPrefix: '会员',
    secondaryStrikethrough: false,
  };
}

export function savingsOf(project: Project): number {
  return Math.max(0, priceOf(project, 'store') - priceOf(project, 'member'));
}

export function isPrimaryFootBathDiy(project: Project): boolean {
  return project.code === 'hxy-qiqing-30';
}

const FOOTBATH_OPTION_CODES = new Set([
  'hxy-qiqing-30',
  'hxy-xiangxiang-60',
  'hxy-xiaoqi-90',
]);
const CATALOG_OPTION_CODES = new Set([
  ...FOOTBATH_OPTION_CODES,
  'hxy-tuina-70',
  'hxy-spa-60',
  'hxy-spa-90',
]);

export function isCatalogOptionsProject(project: Pick<Project, 'code'>): boolean {
  return CATALOG_OPTION_CODES.has(project.code);
}

export function isFootbathOptionsProject(project: Pick<Project, 'code'>): boolean {
  return FOOTBATH_OPTION_CODES.has(project.code);
}

export function supportsFootBathBundle(project: Pick<Project, 'code'>): boolean {
  return project.code === 'hxy-qiqing-30';
}

export function isDetailOnlyProject(project: Pick<Project, 'category' | 'code'>): boolean {
  return project.category === 'kit' || DETAIL_ONLY_CODES.has(project.code);
}

export function isFixedProject(project: Pick<Project, 'category' | 'code'>): boolean {
  return project.category === 'small' || isDetailOnlyProject(project);
}

export function projectCatalogBadge(project: Pick<Project, 'category' | 'code'>): '套盒服务' | '特色服务' | '可加选服务' {
  if (isDetailOnlyProject(project)) return '套盒服务';
  return project.category === 'small' ? '特色服务' : '可加选服务';
}

/** 将项目标签转成顾客能直接理解的说法；只过滤经营内部词。 */
export function projectTagLabel(tag: string): string {
  const normalized = String(tag ?? '').trim();
  if (!normalized || ['小项', '利润款', '基础款', '主力款', '舒享款', '加强项'].includes(normalized)) return '';
  if (normalized === '草本现煮') return '现煮草本';
  if (['按次', '单次'].includes(normalized)) return '单次服务';
  return normalized;
}

type CustomerProjectTagInput = Pick<Project, 'code' | 'category' | 'tags'> & Partial<Pick<Project, 'name' | 'summary' | 'duration_min'>>;

/** 顾客端项目标签统一入口，屏蔽经营内部分类词和历史写法。 */
export function customerProjectTags(project: CustomerProjectTagInput): string[] {
  return customerProjectPurchaseTags(project);
}

const CUSTOMER_PURCHASE_TAGS = new Set([
  '单次服务',
  '可自由搭配',
  '可按需加选',
  '按部位计价',
  '可多选',
  '套盒服务',
  '可搭配局部加强',
]);

function uniqueCustomerTags(tags: string[]): string[] {
  return [...new Set(tags.map(projectTagLabel).filter(Boolean))];
}

/** 顾客可见的选购规则标签：只回答“怎么买”，与项目特色、简介分开。 */
export function customerProjectPurchaseTags(project: CustomerProjectTagInput): string[] {
  if (project.category === 'local-strength' || project.code === 'hxy-jubu-30') {
    return ['按部位计价', '可多选'];
  }
  // 后台 tags 同时承载服务特色和经营标记；这里仅接收顾客能据此完成选择的规则词。
  const configuredRules = uniqueCustomerTags(project.tags || []).filter((label) => CUSTOMER_PURCHASE_TAGS.has(label));
  const fallbackRules = isDetailOnlyProject(project)
    ? ['套盒服务']
    : project.code === 'hxy-qiqing-30'
      ? ['单次服务', '可搭配局部加强']
      : ['单次服务'];
  return uniqueCustomerTags([...fallbackRules, ...configuredRules]);
}

/** 顾客可见的项目特色：只描述服务内容，不暴露后台经营分类。 */
const CUSTOMER_PROJECT_HIGHLIGHTS: Record<string, string[]> = {
  'hxy-qiqing-30': ['现煮草本', '五行茶饮'],
  'hxy-xiangxiang-60': ['现熬草本', '泡脚按摩'],
  'hxy-xiaoqi-90': ['现熬草本', '全身按摩'],
  'hxy-nvshen-60': ['现煮草本', '足部养护', '足膜润足'],
  'hxy-tuina-70': ['全身推拿', '草本热敷'],
  'hxy-spa-60': ['精油护理', '头部按摩', '经络梳'],
  'hxy-spa-90': ['精油护理', '头部按摩', '经络梳'],
  'hxy-taoke-60': ['活络油护理', '工具调理', '草本热敷'],
  'hxy-caier-30': ['耳部清洁', '耳部按摩'],
  'hxy-baguan-1': ['竹罐护理', '草本膏贴'],
  'hxy-guasha-1': ['刮痧护理', '草本膏贴'],
  'hxy-head-30': ['头面耳按摩', '经络梳', '眼罩/眼贴'],
  'hxy-jubu-30': ['局部推拿'],
  'hxy-foot-refine-1': ['现煮草本', '脚底精修'],
};

/** 顾客可见的简介标签：用短语概括时长或组合方式，完整说明仍以 summary 为准。 */
const CUSTOMER_PROJECT_SUMMARY_TAGS: Record<string, string[]> = {
  'hxy-qiqing-30': ['体质检测+泡脚'],
  'hxy-xiangxiang-60': ['60分钟组合'],
  'hxy-xiaoqi-90': ['90分钟组合'],
  'hxy-tuina-70': ['70分钟组合'],
  'hxy-spa-60': ['45+15分钟分段服务'],
  'hxy-spa-90': ['75+15分钟分段服务'],
  'hxy-taoke-60': ['10次/套'],
  'hxy-caier-30': ['30分钟'],
  'hxy-head-30': ['30分钟'],
  'hxy-jubu-30': ['任选一个部位'],
  'hxy-foot-refine-1': ['泡脚+足部修整'],
};

export type CustomerProjectTagGroups = {
  highlights: string[];
  summary: string[];
  purchase: string[];
};

function fallbackProjectHighlights(project: CustomerProjectTagInput): string[] {
  const name = String(project.name || '').trim();
  const summary = String(project.summary || '').trim();
  if (!name) {
    if (/足部|脚部|脚底/.test(summary)) return ['足部护理'];
    if (/采耳|耳部/.test(summary)) return ['耳部清洁'];
    if (/头疗|头部|头面/.test(summary)) return ['头部放松'];
    if (/拔罐/.test(summary)) return ['拔罐护理'];
    if (/刮痧/.test(summary)) return ['刮痧护理'];
    if (/推拿|调理/.test(summary)) return ['身体调理'];
    if (/泡脚|沐足/.test(summary)) return ['草本泡脚'];
    if (/SPA|精油/i.test(summary)) return ['精油护理'];
    if (project.category === 'small') return ['特色护理'];
    if (project.category === 'kit') return ['组合服务'];
    return ['放松调理'];
  }
  if (/足部精修/.test(name)) return ['足部精修', '脚部护理'];
  if (/采耳/.test(name)) return ['耳部清洁', '耳部按摩'];
  if (/头疗|头部/.test(name)) return ['头部放松', '头面护理'];
  if (/拔罐/.test(name)) return ['拔罐护理'];
  if (/刮痧/.test(name)) return ['刮痧护理'];
  if (/推拿|调理/.test(name)) return ['身体调理'];
  if (/泡脚|沐足/.test(name)) return ['草本泡脚'];
  if (/SPA|精油/.test(name)) return ['精油护理'];
  if (project.category === 'small') return [name];
  return ['放松调理'];
}

function fallbackProjectSummaryTags(project: CustomerProjectTagInput): string[] {
  const summary = String(project.summary || '').trim();
  const name = String(project.name || '').trim();
  const text = `${name} ${summary}`;
  const duration = Number(project.duration_min || 0);
  if (duration > 0) return [`${duration}分钟服务`];
  if (/组合/.test(summary)) return ['组合服务'];
  if (/足部精修/.test(text)) return ['脚底精修'];
  if (/采耳/.test(text)) return ['耳部放松'];
  if (/头疗|头部/.test(text)) return ['头部护理'];
  if (/拔罐/.test(text)) return ['单次护理'];
  if (/刮痧/.test(text)) return ['单次护理'];
  if (/推拿|调理/.test(text)) return ['按需调理'];
  if (/泡脚|沐足/.test(text)) return ['草本放松'];
  if (/SPA|精油/i.test(text)) return ['分段护理'];
  if (/局部|部位/.test(summary) || project.category === 'local-strength') return ['局部护理'];
  if (project.category === 'small') return ['单次服务'];
  return summary ? ['到店服务'] : [];
}

/** 三类标签统一去重，避免同一概念在不同职责组重复出现。 */
export function customerProjectTagGroups(project: CustomerProjectTagInput): CustomerProjectTagGroups {
  const used = new Set<string>();
  const takeUnique = (values: string[]) => values.filter((value) => {
    const label = projectTagLabel(value);
    if (!label || used.has(label)) return false;
    used.add(label);
    return true;
  });
  return {
    highlights: takeUnique(customerProjectHighlights(project)),
    summary: takeUnique(customerProjectSummaryTags(project)),
    purchase: takeUnique(customerProjectPurchaseTags(project)),
  };
}

/** 列表最多显示 3 个标签，优先突出服务特色，再补充组合或选购方式。 */
export function customerProjectDisplayTagGroups(project: CustomerProjectTagInput): CustomerProjectTagGroups {
  const groups = customerProjectTagGroups(project);
  // 足部精修的完整服务内容已经放在卡片简介中，列表只保留顾客做决定所需的两个标签，避免重复堆叠。
  if (project.code === 'hxy-foot-refine-1') {
    return {
      highlights: ['脚底精修'],
      summary: [],
      purchase: ['单次服务'],
    };
  }
  let remaining = 3;
  const take = (values: string[], max: number) => {
    const result = values.slice(0, Math.min(max, remaining));
    remaining -= result.length;
    return result;
  };
  const highlights = take(groups.highlights, 2);
  const summary = take(groups.summary, 1);
  const purchase = take(groups.purchase, 1);
  return { highlights, summary, purchase };
}

export function customerProjectHighlights(project: CustomerProjectTagInput): string[] {
  return [...(CUSTOMER_PROJECT_HIGHLIGHTS[project.code] || fallbackProjectHighlights(project))];
}

export function customerProjectSummaryTags(project: CustomerProjectTagInput): string[] {
  return [...(CUSTOMER_PROJECT_SUMMARY_TAGS[project.code] || fallbackProjectSummaryTags(project))];
}

/** 顾客端项目摘要统一入口：后端摘要为空时提供稳定、可读且不暴露经营内部信息的兜底文案。 */
export function customerProjectSummaryText(project: CustomerProjectTagInput): string {
  const configured = String(project.summary || '').trim();
  if (configured) return configured;
  const name = String(project.name || '').trim();
  const byCode: Record<string, string> = {
    'hxy-qiqing-30': '体质检测+现煮草本泡脚+养生茶饮',
    'hxy-xiangxiang-60': '养生茶饮+现煮草本泡脚+肩颈按摩+刮脚搓盐',
    'hxy-xiaoqi-90': '招牌草本泡脚按摩+草本热敷',
    'hxy-nvshen-60': '养生茶饮+现煮草本泡脚+足部养护',
    'hxy-tuina-70': '全身推拿按摩+草木热敷+养生茶饮',
    'hxy-spa-60': '清脚+高端精油SPA+头部按摩+养生茶饮',
    'hxy-spa-90': '清脚+高端精油SPA+头部按摩+养生茶饮',
    'hxy-taoke-60': '痛症调理：活络油+工具+热敷，10次/套',
    'hxy-caier-30': '耳部清洁+耳部按摩',
    'hxy-head-30': '头部轻养按摩+经络梳+眼罩/眼贴',
    'hxy-jubu-30': '肩颈、腰臀、腿部、腹部、足部任选其一',
    'hxy-foot-refine-1': '现煮草本泡脚+脚底精修',
    'hxy-baguan-1': '拔竹罐+草本功效膏贴',
    'hxy-guasha-1': '刮痧+草本功效膏贴',
  };
  if (byCode[project.code]) return byCode[project.code];
  if (name) return name + (project.duration_min ? ` · ${project.duration_min}分钟服务` : ' · 到店服务');
  return project.duration_min ? `${project.duration_min}分钟服务` : '到店服务';
}

/** 三类标签按“特色 → 简介 → 选购”顺序合并，供列表控制展示数量。 */
export function customerProjectDisplayTags(project: CustomerProjectTagInput): string[] {
  const groups = customerProjectTagGroups(project);
  return [...groups.highlights, ...groups.summary, ...groups.purchase];
}

export function diyAddOnProjects(projects: Project[]): Project[] {
  return projects.filter((project) => project.category === 'small');
}

export function formatCouponReminder(coupon: CouponReminder): string {
  return `${coupon.name} · 满${formatMoney(coupon.min_spend_cents)}可减${formatMoney(coupon.amount_cents)}`;
}

export function buildSelectionItems(input: BuildSelectionInput): SelectionItem[] {
  const projectById = new Map(input.projects.map((project) => [project.id, project]));
  const projectCounts = new Map<number, number>();
  for (const id of input.selectedProjectIds) projectCounts.set(id, (projectCounts.get(id) || 0) + 1);
  const items: SelectionItem[] = [...projectCounts]
    .map(([id, quantity]) => ({ project: projectById.get(id), quantity }))
    .filter((entry): entry is { project: Project; quantity: number } => Boolean(entry.project) && entry.project?.category !== 'local-strength')
    .map(({ project, quantity }) => {
      const catalogSelection = input.projectCatalogSelections?.[project.id];
      return {
        project_id: project.id,
        quantity,
        addon_ids: input.projectAddonIds?.[project.id] ?? [],
        diy_preferences: input.projectPreferences?.[project.id] ?? [],
        item_type: 'service' as const,
        chargeable: true,
        ...(catalogSelection ? {
          catalog_version_id: catalogSelection.catalogVersionId,
          option_choice_ids: [...new Set(catalogSelection.optionChoiceIds)],
        } : {}),
      };
    });

  const localProject = input.projects.find((project) => project.category === 'local-strength');
  const partCounts = new Map<string, number>();
  for (const part of input.localParts) partCounts.set(part, (partCounts.get(part) || 0) + 1);
  for (const [part, quantity] of partCounts) {
    items.push({
      project_id: localProject?.id ?? 'local-strength',
      quantity,
      addon_ids: [],
      diy_preferences: [part],
      item_type: 'service',
      chargeable: true,
    });
  }

  if (input.tea) {
    items.push({
      project_id: 'tea',
      quantity: 1,
      addon_ids: [],
      diy_preferences: [input.tea],
      item_type: 'preference',
      chargeable: false,
    });
  }
  return items;
}

function normalizedValues(values: unknown[] | undefined): string[] {
  return [...new Set((values || []).map((value) => String(value)))].sort();
}

function sameSelectionLine(left: SelectionItem, right: SelectionItem): boolean {
  return left.project_id === right.project_id
    && left.item_type === right.item_type
    && left.chargeable === right.chargeable
    && (left.catalog_version_id ?? null) === (right.catalog_version_id ?? null)
    && normalizedValues(left.option_choice_ids).join('\u0001') === normalizedValues(right.option_choice_ids).join('\u0001')
    && normalizedValues(left.addon_ids).join('\u0001') === normalizedValues(right.addon_ids).join('\u0001')
    && normalizedValues(left.diy_preferences).join('\u0001') === normalizedValues(right.diy_preferences).join('\u0001');
}

/**
 * 提交后追加选购时，把原提交快照和当前追加草稿合成一次修订提交。
 * 顾客端草稿可以为空或只包含新增项目，不能覆盖后台已经接收的服务项目。
 */
export function mergeSubmittedSelectionItems(baseItems: SelectionItem[], draftItems: SelectionItem[]): SelectionItem[] {
  const merged: SelectionItem[] = baseItems.map((item) => ({
    ...item,
    addon_ids: [...(item.addon_ids || [])],
    diy_preferences: [...(item.diy_preferences || [])],
    ...(item.option_choice_ids ? { option_choice_ids: [...item.option_choice_ids] } : {}),
  }));

  for (const item of draftItems) {
    // 茶饮是单项偏好，追加新茶饮时替换原茶饮，而不是产生多杯记录。
    if (item.item_type === 'preference' && item.project_id === 'tea') {
      for (let index = merged.length - 1; index >= 0; index -= 1) {
        if (merged[index].item_type === 'preference' && merged[index].project_id === 'tea') merged.splice(index, 1);
      }
      merged.push({ ...item, diy_preferences: [...(item.diy_preferences || [])] });
      continue;
    }

    const existing = merged.find((candidate) => sameSelectionLine(candidate, item));
    if (existing) {
      existing.quantity = Math.max(1, Number(existing.quantity) || 1) + Math.max(1, Number(item.quantity) || 1);
    } else {
      merged.push({
        ...item,
        addon_ids: [...(item.addon_ids || [])],
        diy_preferences: [...(item.diy_preferences || [])],
        ...(item.option_choice_ids ? { option_choice_ids: [...item.option_choice_ids] } : {}),
      });
    }
  }
  return merged;
}

export function calculatePreviewPricing(input: Pick<BuildSelectionInput, 'projects' | 'selectedProjectIds' | 'localParts' | 'projectAddonIds' | 'addons'>): PricingPreview {
  const projectQuantities = new Map<number, number>();
  for (const id of input.selectedProjectIds) projectQuantities.set(id, (projectQuantities.get(id) || 0) + 1);
  const selected = input.projects.filter((project) => (
    projectQuantities.has(project.id) && project.category !== 'local-strength'
  ));
  const localProject = input.projects.find((project) => project.category === 'local-strength');
  const localUnitCount = input.localParts.length;
  const distinctLocalCount = new Set(input.localParts
    .map((part) => part.normalize('NFKC').trim())
    .filter(Boolean)).size;
  const addonById = new Map((input.addons || []).map((addon) => [addon.id, addon]));
  const addonTotals = Object.entries(input.projectAddonIds || {}).reduce((totals, [projectId, addonIds]) => {
    const quantity = projectQuantities.get(Number(projectId)) || 0;
    for (const addonId of new Set(addonIds)) {
      const addon = addonById.get(addonId);
      if (!addon?.chargeable) continue;
      totals.store += addon.prices.store * quantity;
      totals.member += addon.prices.member * quantity;
    }
    return totals;
  }, { store: 0, member: 0 });
  const storeSubtotal = selected.reduce((sum, project) => (
    sum + priceOf(project, 'store') * (projectQuantities.get(project.id) || 0)
  ), 0)
    + (localProject ? priceOf(localProject, 'store') * localUnitCount : 0)
    + addonTotals.store;
  const memberSubtotal = selected.reduce((sum, project) => (
    sum + priceOf(project, 'member') * (projectQuantities.get(project.id) || 0)
  ), 0)
    + (localProject ? priceOf(localProject, 'member') * localUnitCount : 0)
    + addonTotals.member;
  const footBathProject = selected.find(supportsFootBathBundle);
  const qualified = Boolean(footBathProject) && distinctLocalCount >= 2;
  // 两项局部调理：泡脚费按价格带全额减免（门店价 39.9 也全免）。
  const storeAdjustmentCents = qualified && footBathProject ? -priceOf(footBathProject, 'store') : 0;
  const memberAdjustmentCents = qualified && footBathProject ? -priceOf(footBathProject, 'member') : 0;

  return {
    storeSubtotalCents: storeSubtotal,
    memberSubtotalCents: memberSubtotal,
    storeAdjustmentCents,
    memberAdjustmentCents,
    storeTotalCents: Math.max(0, storeSubtotal + storeAdjustmentCents),
    memberTotalCents: Math.max(0, memberSubtotal + memberAdjustmentCents),
    qualified,
  };
}

export function previewPriceForIdentity(preview: Pick<PricingPreview, 'storeTotalCents' | 'memberTotalCents'>, isMember: boolean): number {
  return isMember ? preview.memberTotalCents : preview.storeTotalCents;
}

export function detailPriceComparison(
  preview: Pick<PricingPreview, 'storeTotalCents' | 'memberTotalCents'>,
  isMember: boolean,
): { currentCents: number; currentLabel: '门店价' | '会员价'; comparisonCents: number; comparisonLabel: '门店价' | '会员价' } {
  return isMember
    ? { currentCents: preview.memberTotalCents, currentLabel: '会员价', comparisonCents: preview.storeTotalCents, comparisonLabel: '门店价' }
    : { currentCents: preview.storeTotalCents, currentLabel: '门店价', comparisonCents: preview.memberTotalCents, comparisonLabel: '会员价' };
}

export function detailBasePriceComparison(
  project: Project,
  isMember: boolean,
): { currentCents: number; currentLabel: '门店价' | '会员价'; comparisonCents: number; comparisonLabel: '门店价' | '会员价' } {
  return isMember
    ? { currentCents: priceOf(project, 'member'), currentLabel: '会员价', comparisonCents: priceOf(project, 'store'), comparisonLabel: '门店价' }
    : { currentCents: priceOf(project, 'store'), currentLabel: '门店价', comparisonCents: priceOf(project, 'member'), comparisonLabel: '会员价' };
}

export function calculateDetailPreviewPricing(input: {
  project: Project;
  linkedProjectIds?: number[];
  projects: Project[];
  addons: Addon[];
  addonIds?: number[];
  localParts?: string[];
}): PricingPreview {
  return calculatePreviewPricing({
    projects: input.projects,
    selectedProjectIds: detailPreviewProjectIds(input.project.id, input.linkedProjectIds),
    projectAddonIds: { [input.project.id]: input.addonIds || [] },
    addons: input.addons,
    localParts: detailPreviewLocalParts(input.project, input.localParts || []),
  });
}

export function detailPreviewProjectIds(projectId: number, linkedProjectIds: number[] = []): number[] {
  return [...new Set([projectId, ...linkedProjectIds])];
}

export function detailPreviewLocalParts(project: Pick<Project, 'code'>, parts: string[]): string[] {
  return isFootbathOptionsProject(project as Project) ? parts : [];
}

export function formatMoney(cents: number): string {
  return `¥${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 1)}`;
}

export function projectImage(project: Project): string {
  const generatedAsset = generatedProjectAsset(project.code);
  if (generatedAsset) return assetPath(`projects/${generatedAsset}.webp`);
  if (project.image_url) {
    if (/^https?:\/\//.test(project.image_url)) return project.image_url;
    if (project.image_url.startsWith('/diy/assets/')) return assetPath(project.image_url.slice('/diy/assets/'.length));
    return assetPath(project.image_url.replace(/^\/?assets\//, ''));
  }
  if (project.code === 'hxy-spa-60' || project.code === 'hxy-spa-90') return assetPath('spa-scene.jpg');
  if (project.code === 'hxy-tuina-70') return assetPath('service-tuina.jpg');
  if (project.category === 'local-strength') return assetPath('service-tuina.jpg');
  if (project.category === 'small') return assetPath('daily-care-pack.webp');
  if (project.category === 'kit') return assetPath('family-relax-card.webp');
  return assetPath('service-foot-bath.jpg');
}

const GENERATED_PROJECT_ASSETS = new Set([
  'hxy-qiqing-30', 'hxy-xiangxiang-60', 'hxy-xiaoqi-90', 'hxy-tuina-70', 'hxy-spa-60', 'hxy-spa-90',
  'hxy-taoke-60', 'hxy-caier-30', 'hxy-baguan-1', 'hxy-guasha-1', 'hxy-head-30', 'hxy-jubu-30',
  'hxy-foot-refine-1', 'hxy-nvshen-60',
]);

export function generatedProjectAsset(code: string): string | null {
  return GENERATED_PROJECT_ASSETS.has(code) ? code : null;
}
