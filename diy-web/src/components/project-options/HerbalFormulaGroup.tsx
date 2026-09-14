import type { CatalogOptionGroup } from '../../catalogOptions';

const ELEMENTS: Record<string, { label: string; color: string }> = {
  'formula-wood': { label: '木', color: '#76a580' },
  'formula-fire': { label: '火', color: '#bd8175' },
  'formula-earth': { label: '土', color: '#b59c65' },
  'formula-metal': { label: '金', color: '#a4a393' },
  'formula-water': { label: '水', color: '#709ca3' },
};

export default function HerbalFormulaGroup({ group, selectedChoiceIds, onSelect, readOnly }: {
  group: CatalogOptionGroup;
  selectedChoiceIds: number[];
  onSelect: (id: number) => void;
  readOnly: boolean;
}) {
  const selected = group.choices.find((choice) => selectedChoiceIds.includes(choice.id));
  const element = selected ? ELEMENTS[selected.code] : undefined;
  return (
    <section className="mini-config-card herbal-formula-group" aria-label="今天选哪一方">
      <div className="mini-config-title"><strong>今天选哪一方</strong><span>请选择一方 · 不加价</span></div>
      <div className="herbal-formula-options" role="group" aria-label="草本方">
        {group.choices.map((choice) => {
          const item = ELEMENTS[choice.code];
          return (
            <button key={choice.id} type="button" className={selected?.id === choice.id ? 'active' : ''} aria-label={`${item?.label || ''} ${choice.name}`} aria-pressed={selected?.id === choice.id} disabled={readOnly} onClick={() => onSelect(choice.id)}>
              {item && <i style={{ backgroundColor: item.color }} aria-hidden="true" />}
              <span>{item?.label || choice.name}</span>
            </button>
          );
        })}
      </div>
      {selected && <div className="herbal-formula-detail" aria-live="polite" aria-atomic="true">
        <div><strong>{selected.name}</strong>{element && <span>{element.label}方草本</span>}</div>
        <p>{selected.description}</p>
      </div>}
    </section>
  );
}
