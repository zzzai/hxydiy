import type { Project, SelectionItem } from './domain';
import { hydrateSelectionDraft, linkedProjectIdsForChoices, type SelectionDraft } from './selectionSummary.ts';

type SelectionStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type PrivateSubmitIntent = { signature: string; key: string };
export type PrivateSelectionRecord = {
  storeId: number;
  customerId: number | null;
  sessionId: string;
  accessToken: string;
  items?: SelectionItem[];
  draft?: SelectionDraft;
  submitIntent?: PrivateSubmitIntent;
};


// Wire items omit UI-only references; recover metadata only from matching source versions.
export function restorePrivateSelectionDraft(record: PrivateSelectionRecord, serverItems: Parameters<typeof hydrateSelectionDraft>[0], projects: Project[]): SelectionDraft {
  if (record.draft) return record.draft;
  if (!record.items) return hydrateSelectionDraft(serverItems);
  const choiceKey = (item: SelectionItem) => [...(item.option_choice_ids || [])].sort((a, b) => a - b).join(',');
  return hydrateSelectionDraft(record.items.map((item) => {
    const project = projects.find((candidate) => candidate.id === item.project_id);
    const snapshot = serverItems.find((candidate) => candidate.project_id === item.project_id
      && candidate.catalog_version_id === item.catalog_version_id && choiceKey(candidate) === choiceKey(item));
    const merged = { ...item, category: snapshot?.category ?? project?.category, catalog_selection: snapshot?.catalog_selection };
    if (!merged.catalog_selection && item.catalog_version_id && project?.catalog_version_id === item.catalog_version_id) {
      merged.catalog_selection = { linked_snapshots: linkedProjectIdsForChoices(project.option_groups || [], item.option_choice_ids || [])
        .map((linked_project_id) => ({ linked_project_id })) };
    }
    return merged;
  }));
}

function key(storeId: number) {
  return `hxy_diy_private_selection_${storeId}`;
}

export function readPrivateSelection(storage: SelectionStorage, storeId: number, customerId: number | null): PrivateSelectionRecord | null {
  try {
    const record = JSON.parse(storage.getItem(key(storeId)) || 'null') as PrivateSelectionRecord | null;
    if (!record || record.storeId !== storeId || record.customerId !== customerId
      || typeof record.sessionId !== 'string' || !record.sessionId
      || typeof record.accessToken !== 'string' || !record.accessToken
      || record.items !== undefined && !Array.isArray(record.items)) return null;
    return record;
  } catch {
    return null;
  }
}

export function writePrivateSelection(storage: SelectionStorage, record: PrivateSelectionRecord) {
  storage.setItem(key(record.storeId), JSON.stringify(record));
}

export function clearPrivateSelection(storage: SelectionStorage, storeId: number) {
  storage.removeItem(key(storeId));
}

export function privateSubmitIntent(previous: PrivateSubmitIntent | undefined, signature: string, makeKey = () => crypto.randomUUID()): PrivateSubmitIntent {
  return previous?.signature === signature && previous.key ? previous : { signature, key: makeKey() };
}
