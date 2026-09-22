import type { Addon, Project } from './domain.ts';
import type { CatalogOptionChoice, CatalogOptionGroup, ProjectCatalogSelection } from './catalogOptions.ts';

/**
 * 顾客停留期间的菜单同步间隔。
 * 后端没有菜单版本接口，只能重拉全量后本地比对指纹，因此间隔不能太短。
 * 页面隐藏时会暂停，切回前台与网络恢复时会立即补一次。
 */
export const MENU_SYNC_INTERVAL_MS = 60_000;

function priceSignature(prices: Array<{ price_type: string; amount_cents: number }> | undefined): string {
  return (prices || [])
    .map((price) => `${price.price_type}:${price.amount_cents}`)
    .sort()
    .join(',');
}

function choiceSignature(choice: CatalogOptionChoice): string {
  // 选项上下架与选项价格都会改变顾客可见的金额，必须进入指纹。
  return [choice.id, choice.status, choice.choice_type, choice.charge_mode, priceSignature(choice.prices)].join(':');
}

function groupSignature(group: CatalogOptionGroup): string {
  const choices = (group.choices || []).map(choiceSignature).join(';');
  return [group.id, group.required, group.min_select, group.max_select, choices].join(':');
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
    project.catalog_version_id ?? '',
    priceSignature(project.prices),
    (project.option_groups || []).map(groupSignature).join('/'),
  ].join('|');
}

function addonSignature(addon: Addon): string {
  return [
    addon.id,
    addon.name,
    addon.chargeable,
    addon.can_attach_to_parent,
    addon.independently_sellable,
    addon.prices.store,
    addon.prices.member,
  ].join('|');
}

/**
 * 菜单指纹：只覆盖影响顾客可见菜单、价格和可选项的字段。
 * 图片、详情模块等不影响金额与可选性的变化不触发替换，避免无谓刷新。
 */
export function menuFingerprint(projects: Project[], addons: Addon[]): string {
  return `${projects.map(projectSignature).join('#')}~${addons.map(addonSignature).join('#')}`;
}

export type MenuDraft = {
  selectedProjectIds: number[];
  projectPreferences: Record<number, string[]>;
  projectAddonIds: Record<number, number[]>;
  projectCatalogSelections?: Record<number, ProjectCatalogSelection>;
};

/**
 * 菜单刷新后清理草稿里已经下架的项目。
 * 只移除消失的项目，不改动顾客仍然能选中的部分，避免同步打断选购。
 */
export function pruneDraftToMenu(
  draft: MenuDraft,
  projects: Project[],
): { draft: MenuDraft; removedProjectIds: number[] } {
  const available = new Set(projects.map((project) => project.id));
  const removedProjectIds = [...new Set(draft.selectedProjectIds.filter((id) => !available.has(id)))];
  if (removedProjectIds.length === 0) return { draft, removedProjectIds };

  const projectPreferences = { ...draft.projectPreferences };
  const projectAddonIds = { ...draft.projectAddonIds };
  const projectCatalogSelections = { ...(draft.projectCatalogSelections || {}) };
  for (const id of removedProjectIds) {
    delete projectPreferences[id];
    delete projectAddonIds[id];
    delete projectCatalogSelections[id];
  }

  return {
    draft: {
      ...draft,
      selectedProjectIds: draft.selectedProjectIds.filter((id) => available.has(id)),
      projectPreferences,
      projectAddonIds,
      ...(draft.projectCatalogSelections ? { projectCatalogSelections } : {}),
    },
    removedProjectIds,
  };
}

/** 详情/清单里引用的项目是否仍在当前菜单中；下架后必须收起对应界面。 */
export function isProjectInMenu(projects: Project[], projectId: number | null | undefined): boolean {
  return typeof projectId === 'number' && projects.some((project) => project.id === projectId);
}
