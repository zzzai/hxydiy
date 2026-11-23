import type { ReactNode } from 'react';
import { catalogChoicePriceCents, type CatalogOptionChoice } from '../../catalogOptions';
import { formatMoney, priceGuidanceForPrices, type Project } from '../../domain';

type Props = {
  choice: CatalogOptionChoice | CatalogOptionChoice[];
  parts: string[];
  onToggle?: (part: string, choiceId?: number) => void;
  projects: Project[];
  isMember: boolean;
  readOnly?: boolean;
  children?: ReactNode;
};

function partOf(choice: CatalogOptionChoice) {
  return (choice.body_part || choice.bodyPart || choice.name).normalize('NFKC').trim();
}

export default function LocalStrengthGroup({ choice, parts, onToggle = () => undefined, projects, isMember, readOnly = false, children }: Props) {
  const choices = Array.isArray(choice) ? choice : [choice];
  return (
    <section className="mini-config-card catalog-local-group" aria-label="另加局部服务">
      <div className="mini-config-title"><strong>另加局部服务</strong><span>按部位加时、计费</span></div>
      <div className="mini-local-grid">
        {choices.map((item) => {
          const part = partOf(item);
          const active = parts.includes(part);
          const durationMin = projects.find((project) => project.id === item.linked_project_id)?.duration_min;
          const storeCents = catalogChoicePriceCents(item, projects, false);
          const memberCents = catalogChoicePriceCents(item, projects, true);
          const guidance = priceGuidanceForPrices(storeCents, memberCents, { is_member: isMember });
          return <div className={active ? 'active' : ''} key={item.id}>
            <button type="button" aria-pressed={active} disabled={readOnly || item.status !== 'active'} onClick={() => onToggle(part, item.id)}>
              <span><strong>{part}调理</strong><small>{durationMin ? `加 ${durationMin} 分钟` : '按次服务'}</small></span>
              <span className="addon-price">{item.charge_mode === 'free' ? <em>免费</em> : <><em>+{formatMoney(guidance.primaryCents)}</em>{guidance.memberHintCents !== null && guidance.memberHintCents < guidance.primaryCents && <small>{guidance.hintText.replace('登录享', '登录后享')}</small>}</>}</span>
            </button>
          </div>;
        })}
        {children}
      </div>
    </section>
  );
}
