import { catalogChoicePriceCents, type CatalogOptionChoice } from '../../catalogOptions';
import { displayProjectName, effectivePrice, formatMoney, priceGuidanceForPrices, priceOf, type Project } from '../../domain';

type Props = {
  projects: Project[];
  catalogChoices: CatalogOptionChoice[];
  selectedChoiceIds: number[];
  selectedProjectIds: number[];
  onToggleChoice: (choiceId: number) => void;
  onToggleProject: (projectId: number) => void;
  isMember: boolean;
  readOnly?: boolean;
  embedded?: boolean;
};

export default function RelaxProjectGroup({
  projects,
  catalogChoices,
  selectedChoiceIds,
  selectedProjectIds,
  onToggleChoice,
  onToggleProject,
  isMember,
  readOnly = false,
  embedded = false,
}: Props) {
  const options = projects.filter((project) => project.category !== 'local-strength').map((project) => {
    const choice = catalogChoices.find((item) => item.linked_project_id === project.id && project.category !== 'local-strength');
    const active = choice ? selectedChoiceIds.includes(choice.id) : selectedProjectIds.includes(project.id);
    const storeCents = choice ? catalogChoicePriceCents(choice, projects, false) : priceOf(project, 'store');
    const memberCents = choice ? catalogChoicePriceCents(choice, projects, true) : priceOf(project, 'member');
    const priceCents = choice ? catalogChoicePriceCents(choice, projects, isMember) : effectivePrice(project, isMember);
    const guidance = priceGuidanceForPrices(storeCents, memberCents, { is_member: isMember });
    const toggle = () => {
      if (choice) {
        onToggleChoice(choice.id);
      } else {
        onToggleProject(project.id);
      }
    };
    const button = <button key={project.code} type="button" aria-pressed={active} disabled={readOnly} className={active ? 'active' : ''} onClick={toggle}>
      <span><strong>{displayProjectName(project)}</strong><small>约{project.duration_min || 15}分钟</small></span>
      <span className="addon-price"><em>+{formatMoney(priceCents)}</em>{guidance.memberHintCents !== null && guidance.memberHintCents < guidance.primaryCents && <small>{guidance.hintText.replace('登录享', '登录后享')}</small>}</span>
    </button>;
    return embedded ? <div key={project.code} className={active ? 'active' : ''}>{button}</div> : button;
  });
  if (embedded) return <>{options}</>;
  return (
    <section className="mini-config-card catalog-linked-group relax-project-group" aria-label="再放松一会">
      <div className="mini-config-title"><strong>再放松一会</strong><span>按需加购 · 可多选</span></div>
      <div className="mini-addon-grid">
        {options}
      </div>
    </section>
  );
}
