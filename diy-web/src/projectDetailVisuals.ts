import { assetPath } from './domain.ts';

export type ProjectDetailVisualSection = {
  image: string;
  title: string;
  body: string;
  alt: string;
};

const SIGNATURE_FOOTBATH_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-xiaoqi-90-detail-herbal.webp'),
    title: '一桶温热草本，慢慢泡开',
    body: '从温热草本泡脚开始，让双脚先暖起来，也让整个人慢慢进入放松状态。',
    alt: '荷小悦人物正在为招牌草本沐足准备温热草本木桶',
  },
  {
    image: assetPath('projects/hxy-xiaoqi-90-detail-signature.webp'),
    title: '招牌步骤，更完整地照顾身体',
    body: '草本泡脚、全身按摩（含足部）、刮脚与搓盐共75分钟，再配合15分钟草本热敷和养生茶饮。',
    alt: '荷小悦人物正在整理竹罐、草本热敷包和木质按摩工具',
  },
  {
    image: assetPath('projects/hxy-xiaoqi-90-detail-finish.webp'),
    title: '90 分钟，留足时间慢下来',
    body: '不赶步骤，也不匆忙结束。把一段完整时间留给自己，舒服地坐一会儿。',
    alt: '荷小悦人物坐在新中式沐足椅上享受放松的草本沐足时光',
  },
];

const SPA_60_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-spa-60-detail-1.webp'),
    title: '先泡脚，再安排精油护理',
    body: '这套包含现煮草本泡脚、精油SPA、草本热敷、养生茶饮和养生零食。',
    alt: '荷小悦以手绘国风插画呈现精油、热毛巾、经络梳与护理床的服务准备',
  },
  {
    image: assetPath('projects/hxy-spa-60-detail-2.webp'),
    title: '45 分钟精油护理，按偏好沟通力度',
    body: '精油SPA安排45分钟。精油和手法力度可以选择，服务中也可以向技师说明感受。',
    alt: '荷小悦以手绘国风插画呈现隔巾精油身体舒缓护理',
  },
  {
    image: assetPath('projects/hxy-spa-60-detail-4.webp'),
    title: '15 分钟草本热敷收尾',
    body: '精油护理后搭配15分钟草本热敷；不需要更长的精油护理时，可以从这套开始。',
    alt: '荷小悦以手绘国风插画呈现精油SPA护理用品的整齐收尾',
  },
];

const FOOT_REFINEMENT_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-foot-refine-1-detail.webp'),
    title: '细细整理，给双脚一个清爽收尾',
    body: '包含现煮草本泡脚和足部精细护理。需要清洁或修整哪些位置，请在服务前与门店确认。',
    alt: '荷小悦人物在新中式服务台为顾客进行足部清洁与修整',
  },
];

const GODDESS_FOOT_CARE_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-nvshen-60-detail.webp'),
    title: '从泡脚开始，慢慢照顾双脚',
    body: '现煮草本泡脚、舒缓按摩与足部养护连贯进行，再以足膜和润足收尾，让整个人在温热与香气里放松下来。',
    alt: '荷小悦 IP 在新中式空间为顾客提供草本足护与足膜润足服务',
  },
];

const HERBAL_FOOTBATH_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-qiqing-30-detail-story-v2.webp'),
    title: '一桶草本，慢慢泡开',
    body: '包含AI体质检测、现煮草本泡脚和养生茶饮。不含套餐按摩，想多按一会儿可以另选加购。',
    alt: '荷小悦 IP 准备现煮草本泡、整理草本并在木桶旁品茶的长详情插画',
  },
];

const OIL_BACK_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-oil-back-30-detail.webp'),
    title: '精油准备好，让背部慢慢放松',
    body: '用 30 分钟完成背部精油按摩，力度和细节到店后可以随时沟通。',
    alt: '荷小悦人物在护理床旁准备精油、毛巾与背部护理用品',
  },
];

const CUPPING_SCRAPING_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-cupping-scraping-1-detail.webp'),
    title: '两种选择，按当下需要来',
    body: '拔罐或刮痧任选其一，到店后可以说明偏好，由门店按标准准备器具。',
    alt: '荷小悦人物在护理床旁展示拔罐器具、刮痧板与毛巾',
  },
];

export function projectDetailVisuals(code: string): ProjectDetailVisualSection[] {
  // Preserve existing illustration assets while giving each service distinct copy.
  if (code === 'hxy-xiaoqi-90') return SIGNATURE_FOOTBATH_VISUALS;
  if (code === 'hxy-spa-60') return SPA_60_VISUALS;
  if (code === 'hxy-foot-refine-1') return FOOT_REFINEMENT_VISUALS;
  if (code === 'hxy-nvshen-60') return GODDESS_FOOT_CARE_VISUALS;
  if (code === 'hxy-qiqing-30') return HERBAL_FOOTBATH_VISUALS;
  if (code === 'hxy-oil-back-30') return OIL_BACK_VISUALS;
  if (code === 'hxy-cupping-scraping-1') return CUPPING_SCRAPING_VISUALS;
  const copy: Record<string, [string, string][]> = {
    'hxy-xiangxiang-60': [
      ['泡脚，也多照顾手臂和足底', '现煮草本泡脚搭配手臂及足底按摩、刮脚和搓盐，这部分共50分钟。'],
      ['再留10分钟做草本热敷', '搭配10分钟草本热敷和养生茶饮，整套服务为60分钟。'],
      ['与招牌草本泡有什么不同', '这套按摩重点是手臂和足底；如果想安排全身按摩，可以看看招牌草本泡。'],
    ],
    'hxy-tuina-70': [
      ['60分钟全身推拿', '以全身推拿为主，手法力度可以按偏好选择，也可以在服务中沟通。'],
      ['搭配20分钟艾灸', '推拿后搭配20分钟艾灸，整套服务共80分钟。'],
      ['茶饮和零食也包含在内', '套餐包含养生茶饮和养生零食；额外加购不是必选，不需要时不用添加。'],
    ],
    'hxy-spa-90': [
      ['70分钟精油SPA', '精油护理安排70分钟，比舒压SPA的45分钟更长。'],
      ['背部砭石球，再配草本热敷', '搭配10分钟砭石球背部温通和10分钟草本热敷，护理合计90分钟。'],
      ['泡脚、茶饮和零食也有', '这套还包含现煮草本泡脚、养生茶饮和养生零食；精油与力度可按偏好选择。'],
    ],
    'hxy-jubu-30': [
      ['先选需要照顾的部位', '肩颈、腰臀、腿部、腹部、足部可以分别选择。'],
      ['每个部位单独计价', '合计随所选部位数量变化，未选择时不计入服务。'],
      ['开始前沟通具体位置', '服务时长与安排请向前台确认，不需要的部位不用添加。'],
    ],
    'hxy-baguan-1': [
      ['按需选择拔罐', '作为本次服务的加选，不需要时不用添加。'],
      ['开始前确认部位', '向技师说明需要服务的位置和个人情况。'],
      ['费用看本次清单', '所选内容与费用由前台确认，按现有门店流程结算。'],
    ],
    'hxy-guasha-1': [
      ['按需选择刮痧', '可以作为本次服务的加选，不包含在未标明的套餐中。'],
      ['先说明服务偏好', '具体部位与安排请在开始前向技师确认。'],
      ['不需要就不加选', '加购费用会计入合计，服务后按门店流程结算。'],
    ],
    'hxy-caier-30': [
      ['耳部清洁与按摩', '这项服务包含耳部清洁和耳部按摩，不是全身按摩套餐。'],
      ['可以单独选择', '只需要采耳时可以选择这一项，不必搭配其他主项目。'],
      ['服务前把情况说清楚', '耳部有不适时请先说明；具体时长与服务安排向前台确认。'],
    ],
    'hxy-head-30': [
      ['30分钟头面耳按摩', '以头部、面部和耳部按摩为主，手法力度可以当面沟通。'],
      ['搭配经络梳与眼部用品', '项目还包含经络梳和眼罩或眼贴，具体安排在服务前确认。'],
      ['只做头疗也可以', '不需要全身推拿时，可以单独选这项；加购按个人需要选择。'],
    ],
    'hxy-taoke-60': [
      ['每次60分钟，三段护理', '活络油调理20分钟、工具手法20分钟、热敷20分钟。'],
      ['10次整套，分次使用', '整套包含10次服务，无有效期；页面金额为整套价格，不是单次价格。'],
      ['购买前确认使用方式', '请与前台确认预约、核销和售后规则，了解清楚后再决定是否购买。'],
    ],
  };
  const texts = copy[code];
  if (!texts) return [];
  return texts.map(([title, body], index) => ({
    image: assetPath(`projects/${code}-detail-${index + 1}.webp`),
    title,
    body,
    alt: `荷小悦 IP ${title}`,
  }));
}
