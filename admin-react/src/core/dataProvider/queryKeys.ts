export type QueryParams = Record<string, unknown>;

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value as QueryParams).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, sortValue(item)]));
  return value;
}

export function buildQueryKey(resource: string, params: QueryParams = {}): string {
  return `${resource}:${JSON.stringify(sortValue(params))}`;
}

export function resourceQueryKey(resource: string, id: string | number): string {
  return `${resource}:${String(id)}`;
}
