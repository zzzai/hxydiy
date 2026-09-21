import { validateCatalogSelection, type CatalogOptionChoice, type CatalogOptionGroup, type ProjectCatalogSelection } from './catalogOptions.ts';
import type { Addon, Project } from './domain.ts';

/** Low-frequency polling keeps a long-lived menu current without excessive traffic. */
export const MENU_SYNC_INTERVAL_MS = 60_000;

function priceSignature(prices: Array<{ price_type: string; amount_cents: number }> | undefined): string {
  return (prices || [])
    .map((price) => `${price.price_type}:${price.amount_cents}`)
    .sort()
    .join(',');
}

function choiceSignature(choice: CatalogOptionChoice): string {
  return [
    choice.id,
    choice.name,
    choice.description,
    choice.status,
    choice.choice_type,
    choice.charge_mode,
    choice.linked_project_id ?? '',
    choice.display_order,
    priceSignature(choice.prices),
  ].join(':');
}

function groupSignature(group: CatalogOptionGroup): string {
  return [
    group.id,
    group.name,
    group.description,
    group.selection_mode,
    group.required,
    group.min_select,
    group.max_select,
    group.display_order,
    (group.choices || []).map(choiceSignature).join(';'),
  ].join(':');
}

function projectSignature(project: Project): string {
  return [
    project.id,
    project.code,
    project.name,
    project.category,
    project.duration_min ?? '',
    project.summary,
    project.price_label,
    project.display_order ?? '',
    project.catalog_version_id ?? project.catalog_version ?? '',
    priceSignature(project.prices),
    (project.option_groups || []).map(groupSignature).join('/'),
  ].join('|');
}

function addonSignature(addon: Addon): string {
  return [
    addon.id,
    addon.name,
    addon.parent_project_id ?? '',
    addon.display_order,
    addon.chargeable,
    addon.can_attach_to_parent,
    addon.independently_sellable,
    addon.prices.store,
    addon.prices.member,
  ].join('|');
}

/** Only fields that affect visible menu choices or prices participate. */
export function menuFingerprint(projects: Project[], addons: Addon[]): string {
  return `${projects.map(projectSignature).join('#')}~${addons.map(addonSignature).join('#')}`;
}

export type MenuDraft = {
  selectedProjectIds: number[];
  projectPreferences: Record<number, string[]>;
  projectAddonIds: Record<number, number[]>;
  projectCatalogSelections?: Record<number, ProjectCatalogSelection>;
};

export type MenuReconciliation = {
  draft: MenuDraft;
  removedProjectIds: number[];
  removedAddonIds: number[];
  reselectionProjectIds: number[];
  changed: boolean;
};

function catalogVersionId(project: Project): number | null {
  return project.catalog_version_id ?? project.catalog_version ?? null;
}

function activeChoiceIds(project: Project): Set<number> {
  return new Set(
    (project.option_groups || [])
      .flatMap((group) => group.choices || [])
      .filter((choice) => choice.status === 'active')
      .map((choice) => choice.id),
  );
}

function addonCanAttach(addon: Addon, projectId: number): boolean {
  return addon.can_attach_to_parent && (addon.parent_project_id === null || addon.parent_project_id === projectId);
}

/**
 * Reconcile a local draft with the latest published menu.
 * Invalid projects and catalog selections are removed rather than silently substituted.
 */
export function reconcileDraftToMenu(draft: MenuDraft, projects: Project[], addons: Addon[]): MenuReconciliation {
  const projectById = new Map(projects.map((project) => [project.id, project]));
  const addonById = new Map(addons.map((addon) => [addon.id, addon]));
  const removedProjectIds = new Set<number>();
  const removedAddonIds = new Set<number>();
  const reselectionProjectIds = new Set<number>();

  for (const projectId of new Set(draft.selectedProjectIds)) {
    const project = projectById.get(projectId);
    if (!project) {
      removedProjectIds.add(projectId);
      continue;
    }
    const catalogSelection = draft.projectCatalogSelections?.[projectId];
    const currentVersion = catalogVersionId(project);
    if (!catalogSelection) {
      if (
        currentVersion !== null
        && validateCatalogSelection(project.option_groups || [], []).length > 0
      ) reselectionProjectIds.add(projectId);
      continue;
    }
    const choices = activeChoiceIds(project);
    if (
      currentVersion === null
      || catalogSelection.catalogVersionId !== currentVersion
      || catalogSelection.optionChoiceIds.some((choiceId) => !choices.has(choiceId))
      || validateCatalogSelection(project.option_groups || [], catalogSelection.optionChoiceIds).length > 0
    ) {
      reselectionProjectIds.add(projectId);
    }
  }

  const removedFromDraft = new Set([...removedProjectIds, ...reselectionProjectIds]);
  const selectedProjectIds = draft.selectedProjectIds.filter((projectId) => !removedFromDraft.has(projectId));
  const projectPreferences = { ...draft.projectPreferences };
  const projectAddonIds: Record<number, number[]> = {};
  const projectCatalogSelections = draft.projectCatalogSelections
    ? { ...draft.projectCatalogSelections }
    : undefined;

  for (const projectId of removedFromDraft) {
    delete projectPreferences[projectId];
    delete projectCatalogSelections?.[projectId];
  }

  for (const projectId of new Set(selectedProjectIds)) {
    const validAddonIds = (draft.projectAddonIds[projectId] || []).filter((addonId) => {
      const addon = addonById.get(addonId);
      const valid = Boolean(addon && addonCanAttach(addon, projectId));
      if (!valid) removedAddonIds.add(addonId);
      return valid;
    });
    if (validAddonIds.length > 0) projectAddonIds[projectId] = validAddonIds;
  }

  const nextDraft: MenuDraft = {
    ...draft,
    selectedProjectIds,
    projectPreferences,
    projectAddonIds,
    ...(projectCatalogSelections ? { projectCatalogSelections } : {}),
  };
  const changed = removedFromDraft.size > 0 || removedAddonIds.size > 0;
  return {
    draft: changed ? nextDraft : draft,
    removedProjectIds: [...removedProjectIds],
    removedAddonIds: [...removedAddonIds],
    reselectionProjectIds: [...reselectionProjectIds],
    changed,
  };
}

export function isProjectInMenu(projects: Project[], projectId: number | null | undefined): boolean {
  return typeof projectId === 'number' && projects.some((project) => project.id === projectId);
}

export function shouldApplyMenuSyncResponse(input: {
  requestStoreId: number;
  currentStoreId: number;
  requestId: number;
  latestRequestId: number;
  saving: boolean;
  submitting: boolean;
}): boolean {
  return input.requestStoreId === input.currentStoreId
    && input.requestId === input.latestRequestId
    && !input.saving
    && !input.submitting;
}

export function menuUpdateNotice(result: Pick<MenuReconciliation, 'removedProjectIds' | 'removedAddonIds' | 'reselectionProjectIds'>): string {
  if (result.reselectionProjectIds.length > 0) {
    return `门店菜单已更新，请重新选择 ${result.reselectionProjectIds.length} 个项目`;
  }
  if (result.removedProjectIds.length > 0) {
    return `门店菜单已更新，${result.removedProjectIds.length} 个下架项目已从本次选择中移除`;
  }
  if (result.removedAddonIds.length > 0) {
    return `门店菜单已更新，${result.removedAddonIds.length} 个失效加项已从本次选择中移除`;
  }
  return '门店菜单已更新，价格和可选项已同步';
}

export type MenuSyncContext = {
  currentStoreId: number;
  latestRequestId: number;
  saving: boolean;
  submitting: boolean;
  previousFingerprint: string;
  draft: MenuDraft;
  detailProjectId: number | null;
};

export type MenuSyncUpdate = {
  projects: Project[];
  addons: Addon[];
  fingerprint: string;
  reconciliation: MenuReconciliation;
  detailProject: Project | null;
  detailGone: boolean;
  notice: string;
};

/** Load both menu resources and decide against the latest page state whether the response may land. */
export async function loadMenuSyncUpdate(input: {
  requestStoreId: number;
  requestId: number;
  loadProjects: (storeId: number) => Promise<Project[]>;
  loadAddons: (storeId: number) => Promise<Addon[]>;
  readContext: () => MenuSyncContext;
}): Promise<MenuSyncUpdate | null> {
  const [projects, addons] = await Promise.all([
    input.loadProjects(input.requestStoreId),
    input.loadAddons(input.requestStoreId).catch(() => null),
  ]);
  const context = input.readContext();
  if (
    !addons
    || !shouldApplyMenuSyncResponse({
      requestStoreId: input.requestStoreId,
      currentStoreId: context.currentStoreId,
      requestId: input.requestId,
      latestRequestId: context.latestRequestId,
      saving: context.saving,
      submitting: context.submitting,
    })
  ) return null;

  const fingerprint = menuFingerprint(projects, addons);
  if (fingerprint === context.previousFingerprint) return null;
  const reconciliation = reconcileDraftToMenu(context.draft, projects, addons);
  const detailProject = context.detailProjectId === null
    ? null
    : projects.find((project) => project.id === context.detailProjectId) || null;
  const detailGone = context.detailProjectId !== null && !isProjectInMenu(projects, context.detailProjectId);
  return {
    projects,
    addons,
    fingerprint,
    reconciliation,
    detailProject,
    detailGone,
    notice: menuUpdateNotice(reconciliation),
  };
}
