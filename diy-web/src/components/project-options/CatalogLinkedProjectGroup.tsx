import { catalogChoicePriceCents, type CatalogOptionChoice } from '../../catalogOptions';
import { customerOptionDescription } from '../../customerCopy';
import { formatMoney, priceGuidanceForPrices, type Project } from '../../domain';

type Props = {
  title: string;
  choices: CatalogOptionChoice[];
  selectedChoiceIds: number[];
  onToggle: (choiceId: number) => void;
  projects: Project[];
  isMember: boolean;
  readOnly?: boolean;
};

export default function CatalogLinkedProjectGroup({ title, choices, selectedChoiceIds, onToggle, projects, isMember, readOnly = false }: Props) {
  return (
    <section className="mini-config-card catalog-linked-group" aria-label={title}>
      <div className="mini-config-title"><strong>{title}</strong><span>按需加购 · 可多选</span></div>
      <div className="mini-addon-grid">
        {choices.map((choice) => {
          const active = selectedChoiceIds.includes(choice.id);
          const linkedProject = projects.find((item) => item.id === choice.linked_project_id);
          const durationMin = linkedProject?.duration_min || 15;
          const priceCents = catalogChoicePriceCents(choice, projects, isMember);
          const storeCents = catalogChoicePriceCents(choice, projects, false);
          const memberCents = catalogChoicePriceCents(choice, projects, true);
          const guidance = priceGuidanceForPrices(storeCents, memberCents, { is_member: isMember });
          return <button key={choice.id} type="button" aria-pressed={active} disabled={readOnly || choice.status !== 'active'} className={active ? 'active' : ''} onClick={() => onToggle(choice.id)}>
            <span><strong>{choice.name}</strong><small>{customerOptionDescription(choice.description, durationMin)}</small></span>
            <span className="addon-price">{choice.charge_mode === 'free' ? <em>免费</em> : <><em>+{formatMoney(priceCents)}</em>{guidance.memberHintCents !== null && guidance.memberHintCents < guidance.primaryCents && <small>{guidance.hintText.replace('登录享', '登录后享')}</small>}</>}</span>
          </button>;
        })}
      </div>
    </section>
  );
}
