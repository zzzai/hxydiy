import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clock3,
  Heart,
  TicketPercent,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type { CouponTemplate } from '../api';
import { customerPreferenceLabel, customerPreferenceNote, preferenceSummary, projectDetailActionLabel, shouldShowCouponPrompt } from '../customerCopy';
import { fallbackAttachableAddons, fallbackOptionGroups, withFallbackOptionGroups, type FallbackOptionGroup } from '../projectOptionFallbacks';
import { linkedProjectIdsForChoices, catalogChoicesByType } from '../selectionSummary';
import { catalogDraftResetKey, validateCatalogSelection, withRequiredCatalogDefaults } from '../catalogOptions';
import CatalogLinkedProjectGroup from './project-options/CatalogLinkedProjectGroup';
import LocalStrengthGroup from './project-options/LocalStrengthGroup';
import FootBathBundleProgress from './project-options/FootBathBundleProgress';
import ProjectDetailVisualSections from './ProjectDetailVisualSections';
import { projectDetailVisuals } from '../projectDetailVisuals';
import { motion } from 'framer-motion';
import { detailMotion } from '../motionPresets';
import {
  LOCAL_PARTS,
  calculateDetailPreviewPricing,
  emptyPricingPreview,
  addonPriceOf,
  priceGuidanceForPrices,
  effectivePrice,
  formatCouponReminder,
  formatMoney,
  isCatalogOptionsProject,
  isDetailOnlyProject,
  isFixedProject,
  isPrimaryFootBathDiy,
  isFootbathOptionsProject,
  supportsFootBathBundle,
  detailPreviewProjectIds,
  detailPreviewLocalParts,
  detailBasePriceComparison,
  detailPriceComparison,
  displayProjectName,
  projectImage,
  customerProjectHighlights,
  customerProjectSummaryTags,
  customerProjectPurchaseTags,
  customerProjectTagGroups,
  customerProjectSummaryText,
  type Addon,
  type Project,
} from '../domain';

type ConfirmPayload = {
  project: Project;
  preferences: string[];
  addonIds: number[];
  localParts: string[];
  catalogVersionId?: number;
  optionChoiceIds?: number[];
  linkedProjectIds?: number[];
};

type Props = {
  project: Project | null;
  projects: Project[];
  addons: Addon[];
  selectedProjectIds: number[];
  selectedAddonIds: number[];
  preferences: string[];
  localParts: string[];
  catalogSelection?: { catalogVersionId: number; optionChoiceIds: number[] };
  coupon: CouponTemplate | null;
  positionLabel: string;
  isMember: boolean;
  readOnly?: boolean;
  onClose: () => void;
  onConfirm: (payload: ConfirmPayload) => void;
  onCouponInfo: () => void;
  couponPrompt?: { title?: string; body?: string };
};

export default function ProjectDetailPage({
  project,
  projects,
  addons,
  selectedProjectIds,
  selectedAddonIds,
  preferences,
  localParts,
  catalogSelection,
  coupon,
  positionLabel,
  isMember,
  readOnly = false,
  onClose,
  onConfirm,
  onCouponInfo,
  couponPrompt,
}: Props) {
  const groups = useMemo(() => {
    if (!project) return [];
    if (isDetailOnlyProject(project)) return [];
    if (isCatalogOptionsProject(project) && project.catalog_version_id && (project.option_groups || []).length > 0) return [];
    const configured: FallbackOptionGroup[] = (project.diy_options || [])
      .filter((item) => Array.isArray(item.options) && item.options.length > 0)
      .map((item) => ({ label: item.label, note: item.note || '请选择一项 · 不加价', options: item.options || [] }));
    return configured.length > 0
      ? withFallbackOptionGroups(configured, project.code)
      : fallbackOptionGroups(project.code);
  }, [project]);
  const catalogGroups = useMemo(() => (project?.option_groups || []).filter((group) => group.choices.some((choice) => choice.status === 'active')), [project]);
  const catalogPublished = Boolean(project?.catalog_version_id && catalogGroups.length > 0);
  const catalogChoices = useMemo(() => catalogGroups.flatMap((group) => group.choices).filter((choice) => choice.status === 'active'), [catalogGroups]);
  const catalogLinkedChoices = useMemo(() => catalogChoicesByType(catalogGroups, 'linked_project'), [catalogGroups]);
  const catalogSmallChoices = useMemo(() => catalogLinkedChoices.filter((choice) => projects.some((item) => item.id === choice.linked_project_id && item.category === 'small')), [catalogLinkedChoices, projects]);
  const catalogLocalChoices = useMemo(() => catalogLinkedChoices.filter((choice) => projects.some((item) => item.id === choice.linked_project_id && item.category === 'local-strength')), [catalogLinkedChoices, projects]);
  const catalogPreferenceGroups = useMemo(() => catalogGroups
    .map((group) => ({ ...group, choices: group.choices.filter((choice) => choice.status === 'active' && choice.choice_type === 'preference') }))
    .filter((group) => group.choices.length > 0), [catalogGroups]);
  const attachableAddons = useMemo(() => project && !isDetailOnlyProject(project) ? fallbackAttachableAddons(addons, project.id) : [], [addons, project]);
  const localProject = useMemo(() => projects.find((item) => item.category === 'local-strength') || null, [projects]);
  const isFootBath = Boolean(project && isPrimaryFootBathDiy(project));
  const isCatalogOptions = Boolean(project && isCatalogOptionsProject(project));
  const isFootbathOptions = Boolean(project && isFootbathOptionsProject(project));
  const showBundleProgress = Boolean(project && supportsFootBathBundle(project));
  const detailOnly = Boolean(project && isDetailOnlyProject(project));
  const [choices, setChoices] = useState<string[]>(preferences);
  const [draftAddOnIds, setDraftAddOnIds] = useState<number[]>(selectedAddonIds);
  const [draftLocalParts, setDraftLocalParts] = useState<string[]>(localParts);
  const [draftChoiceIds, setDraftChoiceIds] = useState<number[]>(withRequiredCatalogDefaults(catalogGroups, catalogSelection?.optionChoiceIds || []));
  const draftResetKey = catalogDraftResetKey({
    projectId: project?.id,
    preferences,
    selectedAddonIds,
    localParts,
    catalogVersionId: catalogSelection?.catalogVersionId,
    optionChoiceIds: catalogSelection?.optionChoiceIds || [],
  });

  useEffect(() => {
    setChoices(preferences.length > 0 ? preferences : groups.map((group) => group.options[0]).filter(Boolean));
    setDraftAddOnIds(selectedAddonIds);
    setDraftLocalParts(localParts);
    setDraftChoiceIds(withRequiredCatalogDefaults(catalogGroups, catalogSelection?.optionChoiceIds || []));
  }, [draftResetKey, groups, catalogGroups]);

  useEffect(() => {
    if (!project) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const closeOnEscape = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [project, onClose]);

  const previewSelectedIds = useMemo(() => {
    if (!project) return selectedProjectIds;
    const linkedIds = linkedProjectIdsForChoices(catalogGroups, draftChoiceIds)
      .filter((id) => projects.some((item) => item.id === id && item.category !== 'local-strength'));
    return detailPreviewProjectIds(project.id, linkedIds);
  }, [catalogGroups, draftChoiceIds, project, projects]);

  const preview = useMemo(() => {
    if (!project) {
      return emptyPricingPreview();
    }
    return calculateDetailPreviewPricing({
    project,
    linkedProjectIds: previewSelectedIds.filter((id) => id !== project?.id),
    projects,
    addons,
    addonIds: draftAddOnIds,
    localParts: draftLocalParts,
    });
  }, [projects, previewSelectedIds, draftAddOnIds, addons, draftLocalParts, project]);

  if (!project) return null;
  const displayName = displayProjectName(project);

  const selected = selectedProjectIds.includes(project.id);
  const choose = (group: FallbackOptionGroup, option: string) => {
    if (readOnly) return;
    const withoutGroup = choices.filter((choice) => !group.options.includes(choice));
    setChoices([...withoutGroup, option]);
  };
  const toggleAddOn = (id: number) => {
    if (readOnly) return;
    setDraftAddOnIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };
  const toggleLocalPart = (part: string) => {
    if (readOnly) return;
    setDraftLocalParts((current) => current.includes(part) ? current.filter((item) => item !== part) : [...current, part]);
  };
  const toggleChoice = (choiceId: number) => {
    if (readOnly) return;
    const group = catalogGroups.find((item) => item.choices.some((choice) => choice.id === choiceId));
    setDraftChoiceIds((current) => {
      if (!group) return current;
      const inGroup = new Set(group.choices.map((choice) => choice.id));
      if (group.selection_mode === 'single') {
        return [...current.filter((id) => !inGroup.has(id)), choiceId];
      }
      return current.includes(choiceId) ? current.filter((id) => id !== choiceId) : [...current, choiceId];
    });
  };
  const toggleCatalogLocal = (part: string, choiceId?: number) => {
    if (readOnly) return;
    toggleLocalPart(part);
    if (choiceId !== undefined) toggleChoice(choiceId);
  };
  const selectedCatalogSmallCount = catalogSmallChoices.filter((choice) => draftChoiceIds.includes(choice.id)).length;
  const catalogErrors = catalogPublished ? validateCatalogSelection(catalogGroups, draftChoiceIds) : [];
  const basePrices = detailBasePriceComparison(project, isMember);
  const configuredPrices = detailPriceComparison(preview, isMember);
  const detailVisualSections = projectDetailVisuals(project.code);
  const { highlights: projectHighlights, summary: projectSummaryTags, purchase: projectPurchaseTags } = customerProjectTagGroups(project);

  return (
    <motion.div data-motion="detail" {...detailMotion} className={`project-detail-page mini-detail-page ${isMember ? 'member-active' : ''}`} role="dialog" aria-modal="true" aria-labelledby="project-detail-title">
      <header className="mini-detail-nav">
        <button type="button" aria-label="返回项目列表" onClick={onClose}><ArrowLeft size={22} /></button>
        <strong>项目详情</strong>
        <span>{positionLabel}</span>
      </header>

      <main className="mini-detail-scroll">
        <img className="mini-detail-hero" src={projectImage(project)} alt={`${displayName}服务场景`} />

        <section className="mini-detail-card mini-detail-summary-card">
          <div className="mini-detail-title-row"><h1 id="project-detail-title">{displayName}</h1><Heart size={22} /></div>
          <div className="mini-detail-tags">
            {project.duration_min && <span><Clock3 size={11} />{project.duration_min}分钟</span>}
            <span>价格透明</span>
          </div>
          <p>{customerProjectSummaryText(project)}</p>
          {(projectHighlights.length > 0 || projectSummaryTags.length > 0 || projectPurchaseTags.length > 0) && <div className="customer-tag-groups" aria-label="项目标签">
            {projectHighlights.length > 0 && <div className="customer-tag-group customer-tag-group-highlight"><strong>项目特色</strong><div>{projectHighlights.map((tag) => <span key={tag}>{tag}</span>)}</div></div>}
            {projectSummaryTags.length > 0 && <div className="customer-tag-group customer-tag-group-summary"><strong>项目简介</strong><div>{projectSummaryTags.map((tag) => <span key={tag}>{tag}</span>)}</div></div>}
            {projectPurchaseTags.length > 0 && <div className="customer-tag-group customer-tag-group-purchase"><strong>选购规则</strong><div>{projectPurchaseTags.map((tag) => <span key={tag}>{tag}</span>)}</div></div>}
          </div>}
          <div className="mini-detail-price"><strong>{formatMoney(basePrices.currentCents)}</strong>{isMember ? <del>{basePrices.comparisonLabel} {formatMoney(basePrices.comparisonCents)}</del> : <span className="member-reference-price">会员价 {formatMoney(basePrices.comparisonCents)}</span>}<em>{basePrices.currentLabel}</em></div>
          {!isMember && <small className="price-identity-hint">到店办理年度权益卡，本项目可享会员价 {formatMoney(basePrices.comparisonCents)}</small>}
          {shouldShowCouponPrompt(isMember, detailOnly) && <section className="mini-coupon-card mini-coupon-card-summary" role="button" tabIndex={0} onClick={onCouponInfo} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onCouponInfo(); } }}><TicketPercent size={20} /><div><strong>{coupon ? formatCouponReminder(coupon) : (couponPrompt?.title || '登录领取到店礼遇')}</strong><small>登录后领取，优惠以门店结算为准</small></div><ChevronRight size={17} /></section>}
        </section>

        {!detailOnly && <section className="mini-seat-reminder"><span>服务位置</span><strong>{positionLabel}</strong><small>请确认位置无误</small></section>}

        {groups.map((group, index) => {
          const displayLabel = customerPreferenceLabel(group.label);
          return (
            <section className="mini-config-card" key={group.label} aria-labelledby={`mini-config-${project.id}-${index}`}>
              <div className="mini-config-heading" id={`mini-config-${project.id}-${index}`}>
                <strong>{displayLabel}</strong><span>{customerPreferenceNote(group.note)}</span>
              </div>
              <div className={`mini-option-grid ${displayLabel === '手法力度' ? 'three-col' : 'two-col'}`}>
                {group.options.map((option) => {
                  const active = choices.includes(option);
                  const note = displayLabel === '泡脚液' ? (option === '门店推荐' ? '当日现煮' : '当日可选') : '';
                  return <button key={option} type="button" className={active ? 'active' : ''} aria-pressed={active} onClick={() => choose(group, option)}><strong>{option}</strong>{note && <small>{note}</small>}</button>;
                })}
              </div>
            </section>
          );
        })}

        {isCatalogOptions && !catalogPublished && attachableAddons.length > 0 && (
          <section className="mini-config-card">
            <div className="mini-config-title"><strong>加购服务</strong><span>按需加购 · 可多选</span></div>
            <div className="mini-addon-grid">
              {attachableAddons.map((item) => {
                const active = draftAddOnIds.includes(item.id);
                const addonGuidance = priceGuidanceForPrices(item.prices.store, item.prices.member, { is_member: isMember });
                return <button key={item.id} type="button" disabled={readOnly} className={active ? 'active' : ''} onClick={() => toggleAddOn(item.id)}><span><strong>{item.name}</strong><small>{item.summary || `${item.duration_min || 15}分钟 · 可加选`}</small></span><span className="addon-price">{item.chargeable ? <><em>+{formatMoney(addonGuidance.primaryCents)}</em>{addonGuidance.memberHintCents !== null && addonGuidance.memberHintCents < addonGuidance.primaryCents && <small>{addonGuidance.hintText.replace('登录享', '登录后享')}</small>}</> : <em>免费</em>}</span></button>;
              })}
            </div>
          </section>
        )}

        {isCatalogOptions && catalogPublished && catalogPreferenceGroups.length > 0 && <div className="mini-detail-section-label"><strong>先选服务偏好</strong><span>{preferenceSummary(catalogPreferenceGroups.map((group) => customerPreferenceLabel(group.name)))}</span></div>}

        {isCatalogOptions && catalogPublished && catalogPreferenceGroups.map((group) => (
          <section className="mini-config-card mini-required-options" key={group.id} aria-label={customerPreferenceLabel(group.name)}>
            <div className="mini-config-title"><strong>{customerPreferenceLabel(group.name)}</strong><span>{group.required ? '请选择一项 · 不加价' : '按需选择 · 不加价'}</span></div>
            <div className={`mini-option-grid ${group.selection_mode === 'single' ? (group.choices.length >= 3 ? 'three-col' : 'two-col') : ''}`}>
              {group.choices.map((choice) => (
                <button key={choice.id} type="button" className={draftChoiceIds.includes(choice.id) ? 'active' : ''} aria-pressed={draftChoiceIds.includes(choice.id)} disabled={readOnly} onClick={() => toggleChoice(choice.id)}>
                  <strong>{choice.name}</strong><small>{choice.description || '不加价'}</small>
                </button>
              ))}
            </div>
          </section>
        ))}

        {isCatalogOptions && catalogPublished && catalogSmallChoices.length > 0 && (
          <CatalogLinkedProjectGroup title="加购服务" choices={catalogSmallChoices} selectedChoiceIds={draftChoiceIds} onToggle={toggleChoice} projects={projects} isMember={isMember} readOnly={readOnly} />
        )}

        {isFootbathOptions && catalogPublished && catalogLocalChoices.length > 0 && (
          <LocalStrengthGroup choice={catalogLocalChoices} parts={draftLocalParts} onToggle={toggleCatalogLocal} projects={projects} isMember={isMember} readOnly={readOnly} />
        )}

        {isFootbathOptions && !catalogPublished && localProject && (
          <section className="mini-config-card">
            <div className="mini-config-title"><strong>局部加强</strong><span>按部位加购 · 可多选</span></div>
            <div className="mini-local-grid">
              {LOCAL_PARTS.map((part) => {
                const active = draftLocalParts.includes(part);
                return (
                  <div className={active ? 'active' : ''} key={part}>
                    <button type="button" aria-pressed={active} disabled={readOnly} onClick={() => toggleLocalPart(part)}><span><strong>{part}调理</strong><small>约 {localProject.duration_min || 30} 分钟</small></span><em>+{formatMoney(effectivePrice(localProject, isMember))}</em></button>
                  </div>
                );
              })}
            </div>
            {showBundleProgress && <FootBathBundleProgress preview={preview} selectedParts={draftLocalParts} isMember={isMember} />}
          </section>
        )}

        {showBundleProgress && catalogPublished && <FootBathBundleProgress preview={preview} selectedParts={draftLocalParts} isMember={isMember} />}

        <ProjectDetailVisualSections sections={detailVisualSections} />

        {!detailOnly && !isFootBath && !catalogPublished && groups.length === 0 && <div className="mini-standard-card"><Check size={18} />项目按门店标准服务，到店后可向技师说明偏好。</div>}

        {(project.detail_modules || []).length > 0 && (
          <section className="mini-content-modules">
            {(project.detail_modules || []).map((module, index) => (
              <article key={`${module.title || 'detail'}-${index}`}>
                {module.title && <h2>{module.title}</h2>}
                {module.image_url && <img src={module.image_url} alt="" loading="lazy" decoding="async" />}
                {module.body && <p>{module.body}</p>}
              </article>
            ))}
          </section>
        )}

      </main>

      {(!detailOnly || (project && isFixedProject(project) && project.category === 'small')) && <footer className="mini-detail-footer">
        <div className="mini-detail-total"><span>{configuredPrices.currentLabel}{isMember ? <del>{configuredPrices.comparisonLabel} {formatMoney(configuredPrices.comparisonCents)}</del> : <em>会员价 {formatMoney(configuredPrices.comparisonCents)}</em>}</span><strong>{formatMoney(configuredPrices.currentCents)}</strong></div>
        <div className="mini-detail-actions">
          <button className="primary" type="button" disabled={readOnly || catalogErrors.length > 0} onClick={() => onConfirm({ project, preferences: choices, addonIds: draftAddOnIds, localParts: draftLocalParts, ...(catalogPublished && project.catalog_version_id ? { catalogVersionId: project.catalog_version_id, optionChoiceIds: draftChoiceIds, linkedProjectIds: catalogChoices.filter((choice) => draftChoiceIds.includes(choice.id) && choice.linked_project_id !== null).map((choice) => choice.linked_project_id as number) } : {}) })}>{projectDetailActionLabel(selected, readOnly, catalogErrors.length > 0)}<ChevronRight size={17} /></button>
        </div>
      </footer>}
    </motion.div>
  );
}
