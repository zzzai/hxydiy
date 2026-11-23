import { buildSelectionItems, calculatePreviewPricing, type Addon, type Project, type SelectionItem } from './domain.ts';
import { buildSelectionSummary, type SelectionDraft, type ServicePortion } from './selectionSummary.ts';

type Menu = { projects: Project[]; addons: Addon[] };

export function portionItems(portion: ServicePortion, menu: Menu): SelectionItem[] {
  const items = buildSelectionItems({ ...menu, ...portion.draft });
  const root = items.find(item => item.project_id === portion.projectId);
  return items.map(item => ({
    ...item, service_key: portion.key,
    ...(item === root ? { service_main: true, ...(portion.requested ? { requested_technician_id: portion.requested.id } : {}) } : {}),
  }));
}

export function draftItems(draft: SelectionDraft, menu: Menu) {
  return [...buildSelectionItems({ ...menu, ...draft }), ...(draft.portions || []).flatMap(portion => portionItems(portion, menu))];
}

export function portionPricing(legacy: SelectionDraft, portions: ServicePortion[], menu: Menu) {
  const total = calculatePreviewPricing({ ...menu, ...legacy });
  for (const portion of portions) {
    const price = calculatePreviewPricing({ ...menu, ...portion.draft });
    total.storeSubtotalCents += price.storeSubtotalCents;
    total.memberSubtotalCents += price.memberSubtotalCents;
    total.storeAdjustmentCents += price.storeAdjustmentCents;
    total.memberAdjustmentCents += price.memberAdjustmentCents;
    total.storeTotalCents += price.storeTotalCents;
    total.memberTotalCents += price.memberTotalCents;
    total.qualified ||= price.qualified;
  }
  return total;
}

export function portionsSummary(legacy: SelectionDraft, portions: ServicePortion[], menu: Menu, isMember: boolean) {
  const summary = buildSelectionSummary({ ...menu, draft: legacy, isMember });
  portions.forEach((portion, index) => {
    const { groups } = buildSelectionSummary({ ...menu, draft: portion.draft, isMember });
    if (!groups.length) return;
    const project = menu.projects.find(item => item.id === portion.projectId);
    const pricing = calculatePreviewPricing({ ...menu, ...portion.draft });
    const parts = groups.map(group => {
      const label = group.kind === 'local' || group.target.kind !== 'project' || group.target.projectId !== portion.projectId
        ? [group.title, group.detail] : [group.detail];
      return [...label, ...group.children.map(child => child.title)].filter(Boolean).join(' · ');
    });
    summary.groups.push({
      ...groups[0], key: portion.key, kind: 'project', quantity: 1,
      title: `第 ${index + 1} 份 · ${project?.name || groups[0].title}`,
      detail: [...parts, portion.requested ? `点名 ${portion.requested.label} · 等店长确认` : '门店安排技师'].join(' / '), children: [],
      priceCents: isMember ? pricing.memberTotalCents : pricing.storeTotalCents,
      originalPriceCents: isMember && pricing.memberTotalCents < pricing.storeTotalCents ? pricing.storeTotalCents : null,
      memberPriceCents: !isMember && pricing.memberTotalCents < pricing.storeTotalCents ? pricing.memberTotalCents : null,
      target: { kind: 'project', projectId: portion.projectId, serviceKey: portion.key },
    });
    summary.totalCount += 1;
  });
  return summary;
}

// Merge only independent edits. A competing change to the same portion needs a fresh choice.
export function mergePortionEdits(base: ServicePortion[], local: ServicePortion[], remote: ServicePortion[], menu: Menu) {
  const baseline = new Map(base.map(portion => [portion.key, portion]));
  const result = new Map(remote.map(portion => [portion.key, portion]));
  const edits = new Map(local.map(portion => [portion.key, portion]));
  const signature = (portion?: ServicePortion) => portion
    ? JSON.stringify(portionItems(portion, menu).map(item => [item.project_id, item.quantity, [...item.option_choice_ids || []].sort(), [...item.addon_ids].sort(), item.diy_preferences, item.service_main || false, item.requested_technician_id || null])) : '';
  let conflict = false;
  for (const key of new Set([...baseline.keys(), ...edits.keys()])) {
    const prior = signature(baseline.get(key));
    const wanted = signature(edits.get(key));
    if (prior === wanted) continue;
    const observed = signature(result.get(key));
    if (observed !== prior && observed !== wanted) { conflict = true; continue; }
    const edit = edits.get(key);
    if (edit) result.set(key, edit);
    else result.delete(key);
  }
  return { portions: [...result.values()], conflict };
}
