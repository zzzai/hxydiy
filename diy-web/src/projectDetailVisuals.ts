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
    body: '走竹罐、腰背或腹部重点放松二选一，再配合草本热敷，把细节照顾得更周到。',
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
    title: '护理准备，精油与热巾先就位',
    body: '把精油、热毛巾、经络梳与护理床妥帖备好，先从干净、安静的空间进入舒缓状态。',
    alt: '荷小悦以手绘国风插画呈现精油、热毛巾、经络梳与护理床的服务准备',
  },
  {
    image: assetPath('projects/hxy-spa-60-detail-2.webp'),
    title: '45 分钟精油护理，隔巾轻柔舒缓',
    body: '以完整护理服和毛毯做好遮盖，配合精油与轻柔手法，专注照顾身体的疲惫与紧绷。',
    alt: '荷小悦以手绘国风插画呈现隔巾精油身体舒缓护理',
  },
  {
    image: assetPath('projects/hxy-spa-60-detail-3.webp'),
    title: '15 分钟头部放松，慢慢收束',
    body: '用木质经络梳配合热毛巾，让身体护理之后的放松感自然延续。',
    alt: '荷小悦以手绘国风插画使用木质经络梳为顾客进行头部放松',
  },
  {
    image: assetPath('projects/hxy-spa-60-detail-4.webp'),
    title: '护理用品，整齐收好再结束',
    body: '精油、热毛巾、经络梳与香薰用品整齐归位，把这段舒享体验收得干净、完整。',
    alt: '荷小悦以手绘国风插画呈现精油SPA护理用品的整齐收尾',
  },
];

const FOOT_REFINEMENT_VISUALS: ProjectDetailVisualSection[] = [
  {
    image: assetPath('projects/hxy-foot-refinement-1.webp'),
    title: '细细整理，给双脚一个清爽收尾',
    body: '温水、毛巾和木质工具按门店标准备好，轻松完成足部清洁与修整。',
    alt: '荷小悦人物在新中式服务台为顾客进行足部清洁与修整',
  },
];

export function projectDetailVisuals(code: string): ProjectDetailVisualSection[] {
  // 招牌草本沐足与 60 分钟精油 SPA 使用专属流程插画；其他项目沿用统一信息结构和画风。
  if (code === 'hxy-xiaoqi-90') return SIGNATURE_FOOTBATH_VISUALS;
  if (code === 'hxy-spa-60') return SPA_60_VISUALS;
  if (code === 'hxy-foot-refine-1') return FOOT_REFINEMENT_VISUALS;
  const copy: Record<string, [string, string, string]> = {
    'hxy-qiqing-30': ['一桶草本，先让双脚暖起来', '从温热草本开始，按需要选泡脚液和手法力度。', '泡好之后，服务完成统一线下结算。'],
    'hxy-xiangxiang-60': ['先暖足，再慢慢放松', '给双脚和小腿留出完整时间，按需要自由搭配。', '不赶步骤，按门店最终确认清单服务。'],
    'hxy-tuina-70': ['从肩背开始，慢慢松开', '先选手法力度，再按需要加选服务内容。', '服务完成后统一线下结算。'],
    'hxy-spa-60': ['精油、毛巾和安静的房间', '先选喜欢的精油与手法力度，再按需加选。', '留一段完整时间，安静地照顾自己。'],
    'hxy-spa-90': ['精油、毛巾和安静的房间', '先选喜欢的精油与手法力度，再按需加选。', '留一段完整时间，安静地照顾自己。'],
    'hxy-jubu-30': ['按部位选择，更贴合当下需要', '肩颈、腰臀、腿部、腹部、足部可分别选择。', '局部加强按所选部位计费。'],
    'hxy-baguan-1': ['作为本次服务的加选', '干净的器具、妥帖的准备，按需要轻松加一点。', '具体内容以门店确认清单为准。'],
    'hxy-guasha-1': ['轻轻加一点放松', '玉石工具与草本护理，按需要自由加选。', '服务完成后统一线下结算。'],
    'hxy-caier-30': ['安静享受一段时间', '在舒适的休息椅上，按需要加选采耳服务。', '具体服务以门店确认清单为准。'],
    'hxy-head-30': ['让头部慢慢松下来', '木梳、热巾和舒缓氛围，按需要加选。', '服务完成后统一线下结算。'],
    'hxy-taoke-60': ['一套完整安排', '草本、工具、毛巾与茶饮，按固定内容呈现。', '具体项目、时长和价格以门店最终确认清单为准。'],
  };
  const texts = copy[code];
  if (!texts) return [];
  return texts.map((title, index) => ({
    image: assetPath(`projects/${code}-detail-${index + 1}.webp`),
    title,
    body: index === 0 ? texts[1] : texts[2],
    alt: `荷小悦 IP ${title}`,
  }));
}
