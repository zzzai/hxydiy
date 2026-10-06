import type { Project, SelectionItem } from './domain.ts';

export type ServiceSpec = {
  version: string;
  flow_steps: string[];
  sale_unit: 'service' | 'package';
  services_per_unit: number;
  service_duration_min: number | null;
  included_services: Array<{ code: string; name: string; quantity: number }>;
};

export function includedServiceLabel(spec?: ServiceSpec | null): string {
  return (spec?.included_services || []).map(item => `已含${item.quantity}次${item.name}`).join(' · ');
}

export function serviceUnitLabel(spec?: ServiceSpec | null): string {
  if (spec?.sale_unit !== 'package') return '';
  return `${spec.services_per_unit}次/套${spec.service_duration_min ? ` · 每次${spec.service_duration_min}分钟` : ''}`;
}

export function serviceFacts(spec?: ServiceSpec | null): string {
  return [serviceUnitLabel(spec), includedServiceLabel(spec)].filter(Boolean).join(' · ');
}

export function hasProjectPrice(project: Project, type?: string): boolean {
  return project.prices.some(price => (!type || price.price_type === type) && Number.isFinite(price.amount_cents) && price.amount_cents >= 0);
}

export function additionalIncludedServices(items: SelectionItem[], projects: Project[]): Project[] {
  const byId = new Map(projects.map(project => [String(project.id), project]));
  const selected = items.filter(item => item.item_type === 'service').map(item => byId.get(String(item.project_id))).filter((project): project is Project => Boolean(project));
  const includedCodes = new Set(selected.flatMap(project => project.service_spec?.included_services.map(item => item.code) || []));
  return [...new Map(selected.filter(project => includedCodes.has(project.code)).map(project => [project.id, project])).values()];
}
