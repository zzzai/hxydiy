import {
  addonPriceOf,
  effectivePrice,
  priceOf,
  type Addon,
  type PricingPreview,
  type Project,
  type SelectionItem,
} from './domain.ts';
import type { CatalogOptionChoice, CatalogOptionGroup, ProjectCatalogSelection } from './catalogOptions.ts';

export type SelectionDraft = {
  selectedProjectIds: number[];
  projectPreferences: Record<number, string[]>;
  projectAddonIds: Record<number, number[]>;
  localParts: string[];
  tea: string | null;
  projectCatalogSelections?: Record<number, ProjectCatalogSelection>;
  independentProjectIds?: number[];
  projectLinkedIds?: Record<number, number[]>;
};

// Catalog references share an existing service unit; independent quantities remain intact.
export function selectionProjectIds(independent: number[], links: Record<number, number[]>): number[] {
  const result = [...independent];
  for (const ids of Object.values(links)) for (const id of ids) if (!result.includes(id)) result.push(id);
  return result;
}

export function hydrateSelectionDraft(items: Array<SelectionItem & {
  category?: string; item_kind?: string;
  catalog_selection?: { linked_snapshots?: Array<{ linked_project_id?: number | null }> };
}>): SelectionDraft {
  const draft = emptySelectionDraft();
  const independent: number[] = [];
  const links: Record<number, number[]> = {};
  for (const item of items) {
    const quantity = Math.max(1, Math.min(20, Number(item.quantity) || 1));
    if (item.category === 'local-strength' || item.project_id === 'local-strength') {
      if (item.diy_preferences?.[0]) draft.localParts.push(...Array.from({ length: quantity }, () => item.diy_preferences[0]));
    } else if (typeof item.project_id === 'number') {
      if (item.item_kind !== 'catalog_linked_project') independent.push(...Array.from({ length: quantity }, () => item.project_id as number));
      draft.projectPreferences[item.project_id] = item.diy_preferences || [];
      draft.projectAddonIds[item.project_id] = item.addon_ids || [];
      if (item.catalog_version_id) {
        draft.projectCatalogSelections![item.project_id] = { projectId: item.project_id, catalogVersionId: item.catalog_version_id, optionChoiceIds: item.option_choice_ids || [] };
        links[item.project_id] = [...new Set((item.catalog_selection?.linked_snapshots || []).map(snapshot => snapshot.linked_project_id).filter((id): id is number => typeof id === 'number'))];
      }
    }
  }
  return { ...draft, independentProjectIds: independent, projectLinkedIds: links, selectedProjectIds: selectionProjectIds(independent, links) };
}

export function saveProjectSelection(draft: SelectionDraft, input: {
  projectId: number; preferences: string[]; addonIds: number[]; localParts: string[];
  linkedProjectIds?: number[]; catalogVersionId?: number; optionChoiceIds?: number[];
}): SelectionDraft {
  const independent = [...(draft.independentProjectIds ?? draft.selectedProjectIds)];
  if (!independent.includes(input.projectId)) independent.push(input.projectId);
  const links = { ...draft.projectLinkedIds, [input.projectId]: [...new Set(input.linkedProjectIds || [])].filter(id => id !== input.projectId) };
  return {
    ...draft, independentProjectIds: independent, projectLinkedIds: links,
    selectedProjectIds: selectionProjectIds(independent, links),
    projectPreferences: { ...draft.projectPreferences, [input.projectId]: input.preferences },
    projectAddonIds: { ...draft.projectAddonIds, [input.projectId]: input.addonIds },
    localParts: input.localParts,
    projectCatalogSelections: {
      ...draft.projectCatalogSelections,
      ...(input.catalogVersionId !== undefined && input.optionChoiceIds !== undefined ? { [input.projectId]: {
        projectId: input.projectId, catalogVersionId: input.catalogVersionId, optionChoiceIds: [...new Set(input.optionChoiceIds)],
      } } : {}),
    },
  };
}

export function emptySelectionDraft(): SelectionDraft {
  return {
    selectedProjectIds: [],
    projectPreferences: {},
    projectAddonIds: {},
    projectCatalogSelections: {},
    localParts: [],
    tea: null,
  };
}

export type SelectionTarget =
  | { kind: 'project'; projectId: number }
  | { kind: 'addon'; projectId: number; addonId: number }
  | { kind: 'local'; part: string }
  | { kind: 'tea' };

export function catalogChoicesByType(
  groups: CatalogOptionGroup[],
  choiceType: CatalogOptionChoice['choice_type'],
): CatalogOptionChoice[] {
  return groups.flatMap((group) => group.choices).filter((choice) => (
    choice.status === 'active' && choice.choice_type === choiceType
  ));
}

export function linkedProjectIdsForChoices(groups: CatalogOptionGroup[], choiceIds: number[]): number[] {
  const selected = new Set(choiceIds);
  const linked = new Set<number>();
  for (const choice of groups.flatMap((group) => group.choices)) {
    if (choice.status === 'active' && selected.has(choice.id) && choice.linked_project_id !== null) {
      linked.add(choice.linked_project_id);
    }
  }
  return [...linked];
}

export function bundleProgressCount(preview: { qualified: boolean }, parts: string[]): number {
  return preview.qualified ? 2 : Math.min(new Set(parts.map((part) => part.normalize('NFKC').trim())).size, 2);
}

export type SelectionSummaryChild = {
  key: string;
  kind: 'addon';
  title: string;
  detail: string;
  quantity: number;
  priceCents: number;
  originalPriceCents: number | null;
  memberPriceCents: number | null;
  priceLabel?: '免费';
  target: Extract<SelectionTarget, { kind: 'addon' }>;
};

export type SelectionSummaryGroup = {
  key: string;
  kind: 'project' | 'local' | 'tea';
  title: string;
  detail: string;
  quantity: number;
  priceCents: number;
  originalPriceCents: number | null;
  memberPriceCents: number | null;
  priceLabel?: '赠饮';
  target: Exclude<SelectionTarget, { kind: 'addon' }>;
  children: SelectionSummaryChild[];
};

export type SelectionSummary = {
  groups: SelectionSummaryGroup[];
  totalCount: number;
};

export type ActivePromotion = {
  label: '泡脚组合减免';
  amountCents: number;
};

export function countSelectionDraft(draft: SelectionDraft): number {
  const projectIds = [...new Set(draft.selectedProjectIds)];
  const addonCount = projectIds.reduce((count, projectId) => (
    count + new Set(draft.projectAddonIds[projectId] || []).size
      * draft.selectedProjectIds.filter((id) => id === projectId).length
  ), 0);
  return draft.selectedProjectIds.length + addonCount + draft.localParts.length;
}

export function selectedPreferenceLabels(project: Project, preferences: string[], choiceIds: number[] = []): string[] {
  const selected = new Set(choiceIds);
  const catalogLabels = (project.option_groups || []).flatMap((group) => group.choices)
    .filter((choice) => choice.choice_type === 'preference' && selected.has(choice.id))
    .map((choice) => choice.name);
  return [...new Set([...preferences, ...catalogLabels])];
}

function orderedCounts<T extends string | number>(values: T[]): Array<[T, number]> {
  const counts = new Map<T, number>();
  for (const value of values) counts.set(value, (counts.get(value) || 0) + 1);
  return [...counts.entries()];
}

export function buildSelectionSummary({ projects, addons, draft, isMember }: {
  projects: Project[];
  addons: Addon[];
  draft: SelectionDraft;
  isMember: boolean;
}): SelectionSummary {
  const projectById = new Map(projects.map((project) => [project.id, project]));
  const addonById = new Map(addons.map((addon) => [addon.id, addon]));
  const groups: SelectionSummaryGroup[] = [];

  for (const [projectId, quantity] of orderedCounts(draft.selectedProjectIds)) {
    const project = projectById.get(projectId);
    if (!project || project.category === 'local-strength') continue;
    const children = [...new Set(draft.projectAddonIds[projectId] || [])]
      .map((addonId) => addonById.get(addonId))
      .filter((addon): addon is Addon => Boolean(addon))
      .map((addon) => ({
        key: `addon-${projectId}-${addon.id}`,
        kind: 'addon' as const,
        title: addon.name,
        detail: addon.summary || (addon.duration_min ? `${addon.duration_min}分钟 · 加选项目` : '加选项目'),
        quantity,
        priceCents: addon.chargeable ? addonPriceOf(addon, isMember) * quantity : 0,
        originalPriceCents: addon.chargeable && isMember && addon.prices.store > addon.prices.member
          ? addon.prices.store * quantity
          : null,
        memberPriceCents: addon.chargeable && !isMember && addon.prices.member < addon.prices.store
          ? addon.prices.member * quantity
          : null,
        priceLabel: addon.chargeable ? undefined : '免费' as const,
        target: { kind: 'addon' as const, projectId, addonId: addon.id },
      }));
    groups.push({
      key: `project-${project.id}`,
      kind: 'project',
      title: project.name,
      detail: [project.price_label?.includes('套') ? project.price_label : '', ...selectedPreferenceLabels(project, draft.projectPreferences[project.id] || [], draft.projectCatalogSelections?.[project.id]?.optionChoiceIds)].filter(Boolean).join(' · ') || '按门店标准服务',
      quantity,
      priceCents: effectivePrice(project, isMember) * quantity,
      originalPriceCents: isMember && priceOf(project, 'store') > priceOf(project, 'member')
        ? priceOf(project, 'store') * quantity
        : null,
      memberPriceCents: !isMember && priceOf(project, 'member') < priceOf(project, 'store')
        ? priceOf(project, 'member') * quantity
        : null,
      target: { kind: 'project', projectId: project.id },
      children,
    });
  }

  const localProject = projects.find((project) => project.category === 'local-strength');
  for (const [part, quantity] of orderedCounts(draft.localParts)) {
    groups.push({
      key: `local-${part}`,
      kind: 'local',
      title: `${part}调理`,
      detail: localProject?.duration_min ? `${localProject.duration_min}分钟 · 局部调理` : '按次 · 局部调理',
      quantity,
      priceCents: localProject ? effectivePrice(localProject, isMember) * quantity : 0,
      originalPriceCents: localProject && isMember && priceOf(localProject, 'store') > priceOf(localProject, 'member')
        ? priceOf(localProject, 'store') * quantity
        : null,
      memberPriceCents: localProject && !isMember && priceOf(localProject, 'member') < priceOf(localProject, 'store')
        ? priceOf(localProject, 'member') * quantity
        : null,
      target: { kind: 'local', part },
      children: [],
    });
  }

  return {
    groups,
    totalCount: groups.reduce((count, group) => (
      count + group.quantity + group.children.reduce((childCount, child) => childCount + child.quantity, 0)
    ), 0),
  };
}

export function activePromotion(preview: PricingPreview, isMember: boolean): ActivePromotion | null {
  const amountCents = isMember ? preview.memberAdjustmentCents : preview.storeAdjustmentCents;
  return preview.qualified && amountCents < 0
    ? { label: '泡脚组合减免', amountCents }
    : null;
}

export function removeSelectionEntry(draft: SelectionDraft, target: SelectionTarget, projects: Project[] = []): SelectionDraft {
  if (target.kind === 'project') {
    const projectPreferences = { ...draft.projectPreferences };
    const projectAddonIds = { ...draft.projectAddonIds };
    const projectCatalogSelections = { ...draft.projectCatalogSelections };
    delete projectPreferences[target.projectId];
    delete projectAddonIds[target.projectId];
    delete projectCatalogSelections[target.projectId];
    for (const [id, selection] of Object.entries(projectCatalogSelections)) {
      const linkedChoices = (projects.find(project => project.id === Number(id))?.option_groups || []).flatMap(group => group.choices).filter(choice => choice.linked_project_id === target.projectId).map(choice => choice.id);
      projectCatalogSelections[Number(id)] = { ...selection, optionChoiceIds: selection.optionChoiceIds.filter(choiceId => !linkedChoices.includes(choiceId)) };
    }
    const independent = (draft.independentProjectIds ?? draft.selectedProjectIds).filter(id => id !== target.projectId);
    const links = { ...draft.projectLinkedIds };
    delete links[target.projectId];
    for (const source of Object.keys(links)) links[Number(source)] = links[Number(source)].filter(id => id !== target.projectId);
    return {
      ...draft,
      selectedProjectIds: selectionProjectIds(independent, links),
      ...(draft.independentProjectIds ? { independentProjectIds: independent, projectLinkedIds: links } : {}),
      projectPreferences,
      projectAddonIds,
      projectCatalogSelections,
    };
  }

  if (target.kind === 'addon') {
    const projectAddonIds = { ...draft.projectAddonIds };
    const nextAddonIds = (projectAddonIds[target.projectId] || []).filter((id) => id !== target.addonId);
    if (nextAddonIds.length > 0) projectAddonIds[target.projectId] = nextAddonIds;
    else delete projectAddonIds[target.projectId];
    return { ...draft, projectAddonIds };
  }

  if (target.kind === 'local') {
    return { ...draft, localParts: draft.localParts.filter((part) => part !== target.part) };
  }

  return { ...draft, tea: null };
}

function removeOne<T>(values: T[], target: T): T[] {
  const index = values.lastIndexOf(target);
  return index < 0 ? values : values.filter((_, itemIndex) => itemIndex !== index);
}

export function changeSelectionQuantity(
  draft: SelectionDraft,
  target: Extract<SelectionTarget, { kind: 'project' | 'local' }>,
  delta: 1 | -1,
  projects: Project[] = [],
): SelectionDraft {
  if (target.kind === 'project') {
    const quantity = draft.selectedProjectIds.filter((id) => id === target.projectId).length;
    if (delta > 0 && quantity >= 20) return draft;
    if (delta < 0 && quantity <= 1) return removeSelectionEntry(draft, target, projects);
    const selected = delta > 0 ? [...draft.selectedProjectIds, target.projectId] : removeOne(draft.selectedProjectIds, target.projectId);
    const independent = (draft.independentProjectIds ?? draft.selectedProjectIds).filter(id => id !== target.projectId);
    independent.push(...Array.from({ length: quantity + delta }, () => target.projectId));
    return { ...draft, selectedProjectIds: selected, ...(draft.independentProjectIds ? { independentProjectIds: independent } : {}) };
  }

  const quantity = draft.localParts.filter((part) => part === target.part).length;
  if (delta > 0) {
    return quantity >= 99 ? draft : { ...draft, localParts: [...draft.localParts, target.part] };
  }
  if (quantity <= 1) return removeSelectionEntry(draft, target);
  return { ...draft, localParts: removeOne(draft.localParts, target.part) };
}
