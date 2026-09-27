import type { CSSProperties } from 'react';
import HerbalFormulaDetail from './HerbalFormulaDetail';
import { FOOTBATH_HERBAL_FORMULAS, type HerbalFormulaPresentation } from './herbalFormulaPresentation';

export type HerbalFormula = HerbalFormulaPresentation;
export { FOOTBATH_HERBAL_FORMULAS } from './herbalFormulaPresentation';

export default function FallbackHerbalFormulaGroup({ selectedName, onSelect, readOnly }: {
  selectedName: string | undefined;
  onSelect: (formula: HerbalFormula) => void;
  readOnly: boolean;
}) {
  const selected = FOOTBATH_HERBAL_FORMULAS.find((formula) => formula.value === selectedName || formula.name === selectedName) || FOOTBATH_HERBAL_FORMULAS[0];
  const selectedIndex = FOOTBATH_HERBAL_FORMULAS.findIndex((formula) => formula.code === selected.code);
  const indicatorStyle = {
    '--herbal-columns': FOOTBATH_HERBAL_FORMULAS.length,
    '--herbal-selected-column': selectedIndex + 1,
  } as CSSProperties;

  return (
    <section className="mini-config-card herbal-formula-group" aria-label="现煮泡脚方选择" style={indicatorStyle}>
      <div className="mini-config-title"><strong>现煮泡脚方选择</strong><span>请选择一方 · 不加价</span></div>
      <div className="herbal-formula-options" role="group" aria-label="草本方">
        {FOOTBATH_HERBAL_FORMULAS.map((formula) => {
          const active = formula.code === selected.code;
          return (
            <button key={formula.code} type="button" className={active ? 'active' : ''} aria-label={`${formula.element} ${formula.name}`} aria-pressed={active} disabled={readOnly} onClick={() => onSelect(formula)}>
              <span>{formula.element}</span>
            </button>
          );
        })}
      </div>
      <div className="herbal-formula-indicator" aria-hidden="true"><span /></div>
      <HerbalFormulaDetail formula={selected} />
    </section>
  );
}
