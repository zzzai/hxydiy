import { HERBAL_FORMULA_REMINDER, type HerbalFormulaPresentation } from './herbalFormulaPresentation';
import { assetPath } from '../../domain';

const REPRESENTATIVE_HERBS: Record<string, string> = {
  'formula-metal': '玉竹、百合、麦冬',
  'formula-wood': '玫瑰花、郁金、白芍',
  'formula-water': '杜仲、牛膝、桑寄生',
  'formula-fire': '丹参、当归、鸡血藤',
  'formula-earth': '茯苓、薏苡仁、白术',
};

export default function HerbalFormulaDetail({ formula }: { formula: HerbalFormulaPresentation }) {
  return (
    <div className="herbal-formula-detail" aria-live="polite" aria-atomic="true">
      <div className="herbal-formula-copy">
        <div className="herbal-formula-summary">
          <div>
            <div className="herbal-formula-heading"><strong>{formula.name}</strong></div>
            <p className="herbal-formula-benefit">{formula.benefit}</p>
          </div>
          <img key={formula.code} className="herbal-formula-representatives" src={assetPath(`herbal/${formula.code}-representatives-20260928.webp`)} alt={`代表药材：${REPRESENTATIVE_HERBS[formula.code]}`} decoding="async" onError={(event) => { event.currentTarget.style.visibility = 'hidden'; }} />
        </div>
        <div className="herbal-formula-divider" />
        <strong className="herbal-formula-count">草本配方 · 共{formula.herbs.length}味</strong>
        <p className="herbal-formula-herbs">{formula.herbs.join('、')}</p>
        <p className="herbal-formula-reminder">{HERBAL_FORMULA_REMINDER}</p>
      </div>
    </div>
  );
}
