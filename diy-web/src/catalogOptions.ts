import { LOCAL_PARTS, type Project } from './domain.ts';

export type CatalogOptionPrice = {
  price_type: string;
  amount_cents: number;
  effective_from?: string | null;
  effective_to?: string | null;
};

export type CatalogOptionChoice = {
  id: number;
  code: string;
  name: string;
  description: string;
  choice_type: 'preference' | 'linked_project' | 'dedicated_charge';
  linked_project_id: number | null;
  linked_project_code: string | null;
  linked_catalog_version_id: number | null;
  charge_mode: 'free' | 'inherit_linked_price' | 'custom_price' | string;
  independently_visible: boolean;
  coupon_eligible: boolean;
  annual_gift_eligible: boolean;
  qualifies_for_foot_bath_bundle: boolean;
  display_order: number;
  status: 'active' | 'inactive' | string;
  prices: CatalogOptionPrice[];
  body_part?: string | null;
  bodyPart?: string | null;
};

export type CatalogOptionGroup = {
  id: number;
  code: string;
  name: string;
  description: string;
  selection_mode: 'single' | 'multiple' | string;
  required: boolean;
  min_select: number;
  max_select: number;
  display_order: number;
  choices: CatalogOptionChoice[];
};

export type CatalogSelectionError = {
  code: 'OPTION_CHOICE_DUPLICATE' | 'OPTION_CHOICE_UNKNOWN' | 'OPTION_CHOICE_UNAVAILABLE' | 'OPTION_GROUP_REQUIRED' | 'OPTION_GROUP_MIN_SELECT' | 'OPTION_GROUP_MAX_SELECT';
  groupId?: number;
  choiceId?: number;
};

export type ProjectCatalogSelection = {
  projectId: number;
  catalogVersionId: number;
  optionChoiceIds: number[];
};

export type SelectionDraft = {
  selectedProjectIds?: number[];
  projectPreferences?: Record<number, string[]>;
  projectAddonIds?: Record<number, number[]>;
  localParts?: string[];
  tea?: string | null;
  projectCatalogSelections?: Record<number, ProjectCatalogSelection>;
};

export type LinkedProjectSelection = {
  projectId: number;
  quantity: 1;
  optionChoiceIds: number[];
  bodyPart?: string;
};

type CatalogDraftResetInput = {
  projectId: number | null | undefined;
  preferences: string[];
  selectedAddonIds: number[];
  localParts: string[];
  catalogVersionId: number | null | undefined;
  optionChoiceIds: number[];
};

export function catalogDraftResetKey(input: CatalogDraftResetInput): string {
  return JSON.stringify([
    input.projectId ?? null,
    input.preferences,
    input.selectedAddonIds,
    input.localParts,
    input.catalogVersionId ?? null,
    input.optionChoiceIds,
  ]);
}

function normalizeBodyPart(value: string | null | undefined): string {
  return (value || '').normalize('NFKC').trim();
}

function bodyPartOf(choice: CatalogOptionChoice): string {
  const candidates = [
    normalizeBodyPart(choice.body_part ?? choice.bodyPart),
    normalizeBodyPart(choice.name),
  ];
  return LOCAL_PARTS.find((part) => candidates.some((value) => value === part || value === `${part}调理`)) || '';
}

export function validateCatalogSelection(groups: CatalogOptionGroup[], choiceIds: number[]): CatalogSelectionError[] {
  const errors: CatalogSelectionError[] = [];
  const choicesById = new Map<number, { group: CatalogOptionGroup; choice: CatalogOptionChoice }>();
  for (const group of groups) {
    for (const choice of group.choices) choicesById.set(choice.id, { group, choice });
  }

  const selectedByGroup = new Map<number, number[]>();
  const seen = new Set<number>();
  for (const choiceId of choiceIds) {
    if (seen.has(choiceId)) {
      errors.push({ code: 'OPTION_CHOICE_DUPLICATE', choiceId });
      continue;
    }
    seen.add(choiceId);
    const entry = choicesById.get(choiceId);
    if (!entry) {
      errors.push({ code: 'OPTION_CHOICE_UNKNOWN', choiceId });
      continue;
    }
    if (entry.choice.status !== 'active') {
      errors.push({ code: 'OPTION_CHOICE_UNAVAILABLE', groupId: entry.group.id, choiceId });
      continue;
    }
    const selected = selectedByGroup.get(entry.group.id) || [];
    selected.push(choiceId);
    selectedByGroup.set(entry.group.id, selected);
  }

  for (const group of groups) {
    const selectedCount = (selectedByGroup.get(group.id) || []).length;
    if (group.required && selectedCount === 0) {
      errors.push({ code: 'OPTION_GROUP_REQUIRED', groupId: group.id });
      continue;
    }
    if (selectedCount < group.min_select) errors.push({ code: 'OPTION_GROUP_MIN_SELECT', groupId: group.id });
    if (selectedCount > group.max_select || (group.selection_mode === 'single' && selectedCount > 1)) {
      errors.push({ code: 'OPTION_GROUP_MAX_SELECT', groupId: group.id });
    }
  }
  return errors;
}

/** 为必选目录组补齐稳定默认值；已有选择不被覆盖。 */
export function withRequiredCatalogDefaults(groups: CatalogOptionGroup[], choiceIds: number[]): number[] {
  const next = [...new Set(choiceIds)];
  for (const group of [...groups].sort((a, b) => a.display_order - b.display_order || a.id - b.id)) {
    if (!group.required) continue;
    const activeChoices = group.choices
      .filter((choice) => choice.status === 'active')
      .sort((a, b) => a.display_order - b.display_order || a.id - b.id);
    const selected = activeChoices.filter((choice) => next.includes(choice.id));
    if (selected.length > 0 || activeChoices.length === 0) continue;
    const preferred = group.code === 'pressure'
      ? activeChoices.find((choice) => choice.code === 'pressure-medium' || choice.name === '适中')
      : activeChoices[0];
    if (preferred) next.push(preferred.id);
  }
  return next;
}

export function catalogChoicePriceCents(
  choice: CatalogOptionChoice,
  projects: Project[],
  isMember: boolean,
): number {
  if (choice.choice_type === 'preference' || choice.charge_mode === 'free') return 0;
  const project = choice.linked_project_id === null
    ? null
    : projects.find((item) => item.id === choice.linked_project_id);
  const prices = project?.prices || choice.prices || [];
  const byType = new Map(prices.map((price) => [price.price_type, price.amount_cents]));
  if (isMember) return byType.get('member') ?? byType.get('group') ?? byType.get('store') ?? 0;
  return byType.get('store') ?? byType.get('group') ?? byType.get('member') ?? 0;
}

export function linkedProjectSelections(
  projects: Project[],
  groups: CatalogOptionGroup[],
  choiceIds: number[],
): LinkedProjectSelection[] {
  const projectById = new Map(projects.map((project) => [project.id, project]));
  const choiceById = new Map<number, CatalogOptionChoice>();
  for (const group of groups) {
    for (const choice of group.choices) choiceById.set(choice.id, choice);
  }

  const selections = new Map<string, LinkedProjectSelection>();
  for (const choiceId of new Set(choiceIds)) {
    const choice = choiceById.get(choiceId);
    if (!choice || choice.status !== 'active' || choice.choice_type !== 'linked_project' || choice.linked_project_id === null) continue;
    const project = projectById.get(choice.linked_project_id);
    if (!project) continue;
    const bodyPart = project.category === 'local-strength' ? bodyPartOf(choice) : '';
    if (project.category === 'local-strength' && !bodyPart) continue;
    const key = `${project.id}:${bodyPart}`;
    const existing = selections.get(key);
    if (existing) {
      existing.optionChoiceIds.push(choice.id);
      continue;
    }
    selections.set(key, {
      projectId: project.id,
      quantity: 1,
      optionChoiceIds: [choice.id],
      ...(bodyPart ? { bodyPart } : {}),
    });
  }
  return [...selections.values()];
}

export function applyProjectCatalogSelection<T extends SelectionDraft>(
  draft: T,
  input: ProjectCatalogSelection & {
    parentProjectId?: number;
    choiceIds?: number[];
    linkedProjectIds?: number[];
    localParts?: string[];
  },
): T & { projectCatalogSelections: Record<number, ProjectCatalogSelection> } {
  const projectId = input.projectId ?? input.parentProjectId;
  if (projectId === undefined) throw new Error('catalog selection requires projectId');
  const optionChoiceIds = input.optionChoiceIds ?? input.choiceIds ?? [];
  const selectedProjectIds = draft.selectedProjectIds
    ? [...new Set([...
      draft.selectedProjectIds,
      projectId,
      ...(input.linkedProjectIds || []),
    ])]
    : draft.selectedProjectIds;
  return {
    ...draft,
    ...(selectedProjectIds ? { selectedProjectIds } : {}),
    ...(input.localParts ? { localParts: [...new Set(input.localParts)] } : {}),
    projectCatalogSelections: {
      ...draft.projectCatalogSelections,
      [projectId]: {
        projectId,
        catalogVersionId: input.catalogVersionId,
        optionChoiceIds: [...new Set(optionChoiceIds)],
      },
    },
  };
}
