export const HERBAL_FORMULA_REMINDER = '功效说明为所用药材的常规功效介绍，足浴外用效果仅供参考。';

export type HerbalFormulaCode = 'formula-metal' | 'formula-wood' | 'formula-water' | 'formula-fire' | 'formula-earth';

export type HerbalFormulaPresentation = {
  code: HerbalFormulaCode;
  element: '金' | '木' | '水' | '火' | '土';
  value: string;
  name: string;
  benefit: string;
  herbs: string[];
};

export const FOOTBATH_HERBAL_FORMULAS: HerbalFormulaPresentation[] = [
  {
    code: 'formula-metal', element: '金', value: '清润放松', name: '玉竹百合汤', benefit: '清润舒缓',
    herbs: ['桑叶', '菊花', '芦根', '甘草', '玉竹', '麦冬', '百合', '薄荷', '桔梗', '苦杏仁', '紫苏叶', '桑白皮', '枇杷叶', '陈皮', '艾叶', '鱼腥草'],
  },
  {
    code: 'formula-wood', element: '木', value: '舒心解压', name: '玫瑰郁金汤', benefit: '疏肝调气',
    herbs: ['白芍', '合欢皮', '夜交藤', '玫瑰花', '茯苓', '柴胡', '香附', '郁金', '青皮', '佛手', '远志', '枳壳', '当归', '薄荷', '甘草', '艾叶'],
  },
  {
    code: 'formula-water', element: '水', value: '温暖养护', name: '杜仲菟丝汤', benefit: '固本护腰',
    herbs: ['杜仲', '牛膝', '桑寄生', '艾叶', '干姜', '续断', '狗脊', '五加皮', '淫羊藿', '肉桂', '红花', '补骨脂', '独活', '木瓜', '花椒', '甘草'],
  },
  {
    code: 'formula-fire', element: '火', value: '筋骨轻松', name: '丹参当归汤', benefit: '活络养身',
    herbs: ['桂枝', '艾叶', '当归', '川芎', '丹参', '鸡血藤', '红花', '苏木', '赤芍', '泽兰', '花椒', '干姜', '伸筋草', '甘草'],
  },
  {
    code: 'formula-earth', element: '土', value: '轻盈畅快', name: '茯苓薏仁汤', benefit: '健脾化湿',
    herbs: ['茯苓', '薏苡仁', '白术', '陈皮', '藿香', '艾叶', '泽泻', '苍术', '白扁豆', '赤小豆', '砂仁', '厚朴', '紫苏叶', '山楂', '甘草'],
  },
];

export function herbalFormulaByCode(code: string): HerbalFormulaPresentation | undefined {
  return FOOTBATH_HERBAL_FORMULAS.find((formula) => formula.code === code);
}
