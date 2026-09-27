import { HERBAL_FORMULA_REMINDER, type HerbalFormulaPresentation } from './herbalFormulaPresentation';

export default function HerbalFormulaDetail({ formula }: { formula: HerbalFormulaPresentation }) {
  return (
    <div className="herbal-formula-detail" aria-live="polite" aria-atomic="true">
      <div className="herbal-formula-copy">
        <div className="herbal-formula-heading"><strong>{formula.name}</strong></div>
        <p className="herbal-formula-benefit">{formula.benefit}</p>
        <div className="herbal-formula-divider" />
        <strong className="herbal-formula-count">草本配方 · 共{formula.herbs.length}味</strong>
        <p className="herbal-formula-herbs">{formula.herbs.join('、')}</p>
        <p className="herbal-formula-reminder">{HERBAL_FORMULA_REMINDER}</p>
      </div>
    </div>
  );
}
