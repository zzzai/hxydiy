import { catalogChoicePriceCents, type CatalogOptionChoice } from '../../catalogOptions';
import { customerOptionDescription } from '../../customerCopy';
import { formatMoney, priceGuidanceForPrices, type Project } from '../../domain';

type Props = {
  choice: CatalogOptionChoice | CatalogOptionChoice[];
  parts: string[];
  onToggle?: (part: string, choiceId?: number) => void;
  projects: Project[];
  isMember: boolean;
  readOnly?: boolean;
};

function partOf(choice: CatalogOptionChoice) {
  return (choice.body_part || choice.bodyPart || choice.name).normalize('NFKC').trim();
}

export default function LocalStrengthGroup({ choice, parts, onToggle = () => undefined, projects, isMember, readOnly = false }: Props) {
  const choices = Array.isArray(choice) ? choice : [choice];
  return (
    <section className="mini-config-card catalog-local-group" aria-label="局部加强">
      <div className="mini-config-title"><strong>局部加强</strong><span>按部位加购 · 可多选</span></div>
      <div className="mini-local-grid">
        {choices.map((item) => {
          const part = partOf(item);
          const active = parts.includes(part);
          const durationMin = projects.find((project) => project.id === item.linked_project_id)?.duration_min || 30;
          const storeCents = catalogChoicePriceCents(item, projects, false);
          const memberCents = catalogChoicePriceCents(item, projects, true);
          const guidance = priceGuidanceForPrices(storeCents, memberCents, { is_member: isMember });
          return <div className={active ? 'active' : ''} key={item.id}>
            <button type="button" aria-pressed={active} disabled={readOnly || item.status !== 'active'} onClick={() => onToggle(part, item.id)}>
              <span><strong>{part}调理</strong><small>{customerOptionDescription(item.description, durationMin)}</small></span>
              <span className="addon-price">{item.charge_mode === 'free' ? <em>免费</em> : <><em>+{formatMoney(guidance.primaryCents)}</em>{guidance.memberHintCents !== null && guidance.memberHintCents < guidance.primaryCents && <small>{guidance.hintText.replace('登录享', '登录后享')}</small>}</>}</span>
            </button>
          </div>;
        })}
      </div>
    </section>
  );
}
