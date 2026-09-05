import {
  addonPriceOf,
  effectivePrice,
  priceOf,
  type Addon,
  type PricingPreview,
  type Project,
} from './domain.ts';
import type { CatalogOptionChoice, CatalogOptionGroup, ProjectCatalogSelection } from './catalogOptions.ts';

export type SelectionDraft = {
  selectedProjectIds: number[];
  projectPreferences: Record<number, string[]>;
  projectAddonIds: Record<number, number[]>;
  localParts: string[];
  tea: string | null;
  projectCatalogSelections?: Record<number, ProjectCatalogSelection>;
};

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
  return draft.selectedProjectIds.length + addonCount + draft.localParts.length + (draft.tea ? 1 : 0);
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
        detail: addon.summary || `${addon.duration_min || 15}分钟 · 加选项目`,
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
      detail: draft.projectPreferences[project.id]?.join(' · ') || '按门店标准服务',
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
      detail: localProject ? `${localProject.duration_min || 30}分钟 · 局部调理` : '局部调理',
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

  if (draft.tea) {
    groups.push({
      key: 'tea',
      kind: 'tea',
      title: draft.tea,
      detail: '到店现泡茶饮',
      quantity: 1,
      priceCents: 0,
      originalPriceCents: null,
      memberPriceCents: null,
      priceLabel: '赠饮',
      target: { kind: 'tea' },
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

export function removeSelectionEntry(draft: SelectionDraft, target: SelectionTarget): SelectionDraft {
  if (target.kind === 'project') {
    const projectPreferences = { ...draft.projectPreferences };
    const projectAddonIds = { ...draft.projectAddonIds };
    const projectCatalogSelections = { ...draft.projectCatalogSelections };
    delete projectPreferences[target.projectId];
    delete projectAddonIds[target.projectId];
    delete projectCatalogSelections[target.projectId];
    return {
      ...draft,
      selectedProjectIds: draft.selectedProjectIds.filter((id) => id !== target.projectId),
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
): SelectionDraft {
  if (target.kind === 'project') {
    const quantity = draft.selectedProjectIds.filter((id) => id === target.projectId).length;
    if (delta > 0) {
      return quantity >= 99
        ? draft
        : { ...draft, selectedProjectIds: [...draft.selectedProjectIds, target.projectId] };
    }
    if (quantity <= 1) return removeSelectionEntry(draft, target);
    return { ...draft, selectedProjectIds: removeOne(draft.selectedProjectIds, target.projectId) };
  }

  const quantity = draft.localParts.filter((part) => part === target.part).length;
  if (delta > 0) {
    return quantity >= 99 ? draft : { ...draft, localParts: [...draft.localParts, target.part] };
  }
  if (quantity <= 1) return removeSelectionEntry(draft, target);
  return { ...draft, localParts: removeOne(draft.localParts, target.part) };
}
