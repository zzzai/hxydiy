import type { DataProvider } from '@refinedev/core';
import { dataProvider as adminProvider } from './index.ts';

type LegacyProvider = Pick<typeof adminProvider, 'getList' | 'getOne' | 'create' | 'update' | 'remove'>;

type RefineProviderOptions = Partial<LegacyProvider>;

function paginationParams(pagination?: { current?: number; currentPage?: number; pageSize?: number; mode?: string }) {
  if (!pagination || pagination.mode === 'off') return {};
  const current = pagination.current ?? pagination.currentPage;
  return {
    ...(current ? { page: current } : {}),
    ...(pagination.pageSize ? { page_size: pagination.pageSize } : {}),
  };
}

function filterParams(filters?: readonly { field?: string; value?: unknown; operator?: string }[]) {
  return Object.fromEntries(
    (filters || [])
      .filter((filter) => filter.field && filter.value !== undefined && filter.value !== null && filter.value !== '')
      .map((filter) => [filter.field as string, filter.value]),
  );
}

export function createRefineDataProvider(overrides: RefineProviderOptions = {}): DataProvider {
  const legacy = {
    getList: overrides.getList || adminProvider.getList.bind(adminProvider),
    getOne: overrides.getOne || adminProvider.getOne.bind(adminProvider),
    create: overrides.create || adminProvider.create.bind(adminProvider),
    update: overrides.update || adminProvider.update.bind(adminProvider),
    remove: overrides.remove || adminProvider.remove.bind(adminProvider),
  };
  return {
    getApiUrl: () => '/api/v1',
    async getList({ resource, pagination, filters }) {
      const result = await legacy.getList(resource, {
        ...paginationParams(pagination),
        ...filterParams(filters),
      });
      const data = Array.isArray(result)
        ? result
        : ((result as { data?: unknown[]; items?: unknown[] }).data
          || (result as { items?: unknown[] }).items
          || []);
      const total = Array.isArray(result) ? data.length : Number((result as { total?: number }).total ?? data.length);
      return { data: data as never[], total };
    },
    async getOne({ resource, id }) {
      return { data: await legacy.getOne(resource, id) as never };
    },
    async create({ resource, variables }) {
      return { data: await legacy.create(resource, variables as Record<string, unknown>) as never };
    },
    async update({ resource, id, variables }) {
      return { data: await legacy.update(resource, id, variables as Record<string, unknown>) as never };
    },
    async deleteOne({ resource, id }) {
      return { data: await legacy.remove(resource, id) as never };
    },
  };
}

export const refineDataProvider = createRefineDataProvider();
