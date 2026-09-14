import type { CatalogOptionGroup } from '../../catalogOptions';
import type { CSSProperties } from 'react';
import { assetPath } from '../../domain';

const ELEMENTS: Record<string, { label: string; color: string }> = {
  'formula-wood': { label: '木', color: '#329345' },
  'formula-fire': { label: '火', color: '#f0524c' },
  'formula-earth': { label: '土', color: '#c88b29' },
  'formula-metal': { label: '金', color: '#c49334' },
  'formula-water': { label: '水', color: '#0798db' },
};

export default function HerbalFormulaGroup({ group, selectedChoiceIds, onSelect, readOnly }: {
  group: CatalogOptionGroup;
  selectedChoiceIds: number[];
  onSelect: (id: number) => void;
  readOnly: boolean;
}) {
  const order = Object.keys(ELEMENTS);
  const choices = [...group.choices].sort((a, b) => {
    const rank = (code: string) => order.includes(code) ? order.indexOf(code) : order.length;
    return rank(a.code) - rank(b.code);
  });
  const selected = choices.find((choice) => selectedChoiceIds.includes(choice.id));
  const element = selected ? ELEMENTS[selected.code] : undefined;
  const count = Math.max(1, group.choices.length);
  const selectedIndex = choices.findIndex((choice) => choice.id === selected?.id);
  const center = (Math.max(0, selectedIndex) + 0.5) / count;
  const indicatorStyle = {
    '--herbal-columns': count,
    '--herbal-anchor': `calc(${center * 100}% + ${(center - 0.5)} * var(--herbal-gap))`,
    '--herbal-color': element?.color || '#176856',
  } as CSSProperties;
  return (
    <section className="mini-config-card herbal-formula-group" aria-label="先选服务偏好" style={indicatorStyle}>
      <div className="herbal-formula-title"><strong>先选服务偏好</strong><span>为你推荐更合适的草本与手法</span></div>
      <div className="herbal-formula-options" role="group" aria-label="草本方">
        {choices.map((choice) => {
          const item = ELEMENTS[choice.code];
          return (
            <button key={choice.id} type="button" className={selected?.id === choice.id ? 'active' : ''} aria-label={`${item?.label || ''} ${choice.name}`} aria-pressed={selected?.id === choice.id} disabled={readOnly} onClick={() => onSelect(choice.id)}>
              {item && <i style={{ color: item.color }} aria-hidden="true">{item.label}</i>}
              <span>{choice.name}</span>
            </button>
          );
        })}
      </div>
      {selected && <div className="herbal-formula-detail" aria-live="polite" aria-atomic="true">
        {element && <div className="herbal-formula-art" aria-hidden="true"><img src={assetPath(`herbal/${selected.code}.webp`)} alt="" /></div>}
        <div className="herbal-formula-copy">
          <div className="herbal-formula-heading"><strong>{selected.name}</strong>{element && <span>{element.label}方草本</span>}</div>
          <p>{selected.description}</p>
        </div>
        {element && <div className="herbal-formula-caption" aria-hidden="true"><span>{element.label}方草本</span><span>{selected.name}</span></div>}
      </div>}
    </section>
  );
}
