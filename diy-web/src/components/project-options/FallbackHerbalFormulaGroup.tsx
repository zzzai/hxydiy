import type { CSSProperties } from 'react';

import { assetPath } from '../../domain';

export type HerbalFormula = {
  code: 'formula-wood' | 'formula-fire' | 'formula-earth' | 'formula-metal' | 'formula-water';
  name: string;
  description: string;
};

const ELEMENTS: Record<HerbalFormula['code'], { label: string; color: string }> = {
  'formula-wood': { label: '木', color: '#329345' },
  'formula-fire': { label: '火', color: '#f0524c' },
  'formula-earth': { label: '土', color: '#c88b29' },
  'formula-metal': { label: '金', color: '#c49334' },
  'formula-water': { label: '水', color: '#0798db' },
};

export const FOOTBATH_HERBAL_FORMULAS: HerbalFormula[] = [
  { code: 'formula-wood', name: '舒心解压', description: '最近有点忙，想松一松\n玫瑰花 · 佛手 · 合欢皮' },
  { code: 'formula-fire', name: '筋骨轻松', description: '久坐久站，想舒展一下\n桂枝 · 丹参 · 鸡血藤' },
  { code: 'formula-earth', name: '轻盈畅快', description: '身体沉沉的，想轻松一点\n茯苓 · 薏苡仁 · 陈皮' },
  { code: 'formula-metal', name: '清润放松', description: '想清清爽爽地放松一下\n桑叶 · 菊花 · 百合' },
  { code: 'formula-water', name: '温暖养护', description: '手脚容易凉，想暖一暖\n杜仲 · 桑寄生 · 淫羊藿' },
];

export default function FallbackHerbalFormulaGroup({ selectedName, onSelect, readOnly }: {
  selectedName: string | undefined;
  onSelect: (formula: HerbalFormula) => void;
  readOnly: boolean;
}) {
  const selected = FOOTBATH_HERBAL_FORMULAS.find((formula) => formula.name === selectedName) || FOOTBATH_HERBAL_FORMULAS[0];
  const selectedIndex = FOOTBATH_HERBAL_FORMULAS.findIndex((formula) => formula.code === selected.code);
  const element = ELEMENTS[selected.code];
  const indicatorStyle = {
    '--herbal-columns': FOOTBATH_HERBAL_FORMULAS.length,
    '--herbal-selected-column': selectedIndex + 1,
    '--herbal-color': element.color,
  } as CSSProperties;

  return (
    <section className="mini-config-card herbal-formula-group" aria-label="现煮泡脚方选择" style={indicatorStyle}>
      <div className="mini-config-title"><strong>现煮泡脚方选择</strong><span>请选择一方 · 不加价</span></div>
      <div className="herbal-formula-options" role="group" aria-label="草本方">
        {FOOTBATH_HERBAL_FORMULAS.map((formula) => {
          const item = ELEMENTS[formula.code];
          const active = formula.code === selected.code;
          return (
            <button key={formula.code} type="button" className={active ? 'active' : ''} aria-label={`${item.label} ${formula.name}`} aria-pressed={active} disabled={readOnly} onClick={() => onSelect(formula)}>
              <span style={{ color: item.color }}>{item.label}</span>
            </button>
          );
        })}
      </div>
      <div className="herbal-formula-indicator" aria-hidden="true"><span /></div>
      <div className="herbal-formula-detail" aria-live="polite" aria-atomic="true">
        <div className="herbal-formula-art" aria-hidden="true"><img src={assetPath(`herbal/${selected.code}.webp`)} alt="" /></div>
        <div className="herbal-formula-copy">
          <div className="herbal-formula-heading"><strong>{selected.name}</strong><span>{element.label}方草本</span></div>
          <p>{selected.description}</p>
        </div>
        <div className="herbal-formula-caption" aria-hidden="true"><span>{element.label}方草本</span><span>{selected.name}</span></div>
      </div>
    </section>
  );
}
