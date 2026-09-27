import type { CatalogOptionGroup } from '../../catalogOptions';
import type { CSSProperties } from 'react';
import HerbalFormulaDetail from './HerbalFormulaDetail';
import { FOOTBATH_HERBAL_FORMULAS, herbalFormulaByCode } from './herbalFormulaPresentation';

export default function HerbalFormulaGroup({ group, selectedChoiceIds, onSelect, readOnly }: {
  group: CatalogOptionGroup;
  selectedChoiceIds: number[];
  onSelect: (id: number) => void;
  readOnly: boolean;
}) {
  const order: string[] = FOOTBATH_HERBAL_FORMULAS.map((formula) => formula.code);
  const choices = [...group.choices].sort((a, b) => {
    const rank = (code: string) => order.includes(code) ? order.indexOf(code) : order.length;
    return rank(a.code) - rank(b.code);
  });
  const selected = choices.find((choice) => selectedChoiceIds.includes(choice.id));
  const formula = selected ? herbalFormulaByCode(selected.code) : undefined;
  const count = Math.max(1, group.choices.length);
  const selectedIndex = choices.findIndex((choice) => choice.id === selected?.id);
  const indicatorStyle = {
    '--herbal-columns': count,
    '--herbal-selected-column': Math.max(0, selectedIndex) + 1,
  } as CSSProperties;
  return (
    <section className="mini-config-card herbal-formula-group" aria-label="现煮泡脚方选择" style={indicatorStyle}>
      <div className="mini-config-title"><strong>现煮泡脚方选择</strong><span>请选择一方 · 不加价</span></div>
      <div className="herbal-formula-options" role="group" aria-label="草本方">
        {choices.map((choice) => {
          const item = herbalFormulaByCode(choice.code);
          return (
            <button key={choice.id} type="button" className={selected?.id === choice.id ? 'active' : ''} aria-label={`${item?.element || ''} ${item?.name || choice.name}`} aria-pressed={selected?.id === choice.id} disabled={readOnly} onClick={() => onSelect(choice.id)}>
              <span>{item?.element || choice.name}</span>
            </button>
          );
        })}
      </div>
      {selected && <div className="herbal-formula-indicator" aria-hidden="true"><span /></div>}
      {formula && <HerbalFormulaDetail formula={formula} />}
    </section>
  );
}
