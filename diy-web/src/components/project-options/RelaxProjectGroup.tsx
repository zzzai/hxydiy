import { useState } from 'react';

import { catalogChoicePriceCents, type CatalogOptionChoice } from '../../catalogOptions';
import { customerOptionDescription } from '../../customerCopy';
import { LOCAL_PARTS, displayProjectName, effectivePrice, formatMoney, priceGuidanceForPrices, priceOf, type Project } from '../../domain';

type Props = {
  projects: Project[];
  catalogChoices: CatalogOptionChoice[];
  selectedChoiceIds: number[];
  selectedProjectIds: number[];
  localParts: string[];
  onToggleChoice: (choiceId: number) => void;
  onToggleProject: (projectId: number) => void;
  onToggleLocalPart: (part: string, choiceId?: number) => void;
  isMember: boolean;
  readOnly?: boolean;
};

function bodyPart(choice: CatalogOptionChoice): string {
  return (choice.body_part || choice.bodyPart || choice.name).normalize('NFKC').trim();
}

export default function RelaxProjectGroup({
  projects,
  catalogChoices,
  selectedChoiceIds,
  selectedProjectIds,
  localParts,
  onToggleChoice,
  onToggleProject,
  onToggleLocalPart,
  isMember,
  readOnly = false,
}: Props) {
  const [localExpanded, setLocalExpanded] = useState(localParts.length > 0);
  const localProject = projects.find((project) => project.category === 'local-strength');

  return (
    <section className="mini-config-card catalog-linked-group relax-project-group" aria-label="再放松一会">
      <div className="mini-config-title"><strong>再放松一会</strong><span>按需加购 · 可多选</span></div>
      <div className="mini-addon-grid">
        {projects.map((project) => {
          const choice = catalogChoices.find((item) => item.linked_project_id === project.id && project.category !== 'local-strength');
          const active = project.category === 'local-strength'
            ? localParts.length > 0
            : choice ? selectedChoiceIds.includes(choice.id) : selectedProjectIds.includes(project.id);
          const storeCents = choice ? catalogChoicePriceCents(choice, projects, false) : priceOf(project, 'store');
          const memberCents = choice ? catalogChoicePriceCents(choice, projects, true) : priceOf(project, 'member');
          const priceCents = choice ? catalogChoicePriceCents(choice, projects, isMember) : effectivePrice(project, isMember);
          const guidance = priceGuidanceForPrices(storeCents, memberCents, { is_member: isMember });
          const toggle = () => {
            if (project.category === 'local-strength') {
              setLocalExpanded((current) => !current);
            } else if (choice) {
              onToggleChoice(choice.id);
            } else {
              onToggleProject(project.id);
            }
          };
          return <button key={project.code} type="button" aria-pressed={active} disabled={readOnly} className={active ? 'active' : ''} onClick={toggle}>
            <span><strong>{displayProjectName(project)}</strong><small>{customerOptionDescription(project.summary, project.duration_min || 15)}</small></span>
            <span className="addon-price"><em>+{formatMoney(priceCents)}</em>{guidance.memberHintCents !== null && guidance.memberHintCents < guidance.primaryCents && <small>{guidance.hintText.replace('登录享', '登录后享')}</small>}</span>
          </button>;
        })}
      </div>
      {localExpanded && localProject && <div className="mini-local-grid relax-local-parts" aria-label="选择局部推拿部位">
        {LOCAL_PARTS.map((part) => {
          const choice = catalogChoices.find((item) => item.linked_project_id === localProject.id && bodyPart(item) === part);
          const active = localParts.includes(part);
          const storeCents = choice ? catalogChoicePriceCents(choice, projects, false) : priceOf(localProject, 'store');
          const memberCents = choice ? catalogChoicePriceCents(choice, projects, true) : priceOf(localProject, 'member');
          const guidance = priceGuidanceForPrices(storeCents, memberCents, { is_member: isMember });
          return <div className={active ? 'active' : ''} key={part}><button type="button" aria-pressed={active} disabled={readOnly} onClick={() => onToggleLocalPart(part, choice?.id)}>
            <span><strong>{part}调理</strong><small>约 {localProject.duration_min || 30} 分钟</small></span>
            <span className="addon-price"><em>+{formatMoney(guidance.primaryCents)}</em>{guidance.memberHintCents !== null && guidance.memberHintCents < guidance.primaryCents && <small>{guidance.hintText.replace('登录享', '登录后享')}</small>}</span>
          </button></div>;
        })}
      </div>}
    </section>
  );
}
