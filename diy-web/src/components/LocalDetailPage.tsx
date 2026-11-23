import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { LOCAL_DETAIL_PROFILES, LOCAL_PARTS, displayProjectName, effectivePrice, formatMoney, priceOf, projectImage, type Project } from '../domain';
import { motion } from 'framer-motion';
import { detailMotion } from '../motionPresets';
import DetailIntroduction from './DetailIntroduction';
import DetailPrice from './DetailPrice';

type Props = {
  open: boolean;
  project: Project | null;
  selectedParts: string[];
  technicianPicker?: import('react').ReactNode;
  positionLabel: string;
  isMember: boolean;
  readOnly?: boolean;
  unseated?: boolean;
  onClose: () => void;
  onConfirm: (parts: string[]) => void;
};

export default function LocalDetailPage({ open, project, selectedParts, technicianPicker, positionLabel, isMember, readOnly = false, unseated = false, onClose, onConfirm }: Props) {
  const [draft, setDraft] = useState<string[]>(selectedParts);
  const [focusedPart, setFocusedPart] = useState<string>(selectedParts[0] || LOCAL_PARTS[0]);

  useEffect(() => {
    if (open) {
      setDraft(selectedParts);
      setFocusedPart(selectedParts[0] || LOCAL_PARTS[0]);
    }
  }, [open, selectedParts]);

  const total = useMemo(() => project ? effectivePrice(project, isMember) * draft.length : 0, [project, isMember, draft.length]);
  if (!open || !project) return null;

  const toggle = (part: string) => {
    setFocusedPart(part);
    setDraft((current) => current.includes(part) ? current.filter((item) => item !== part) : [...current, part]);
  };
  const activeProfile = LOCAL_DETAIL_PROFILES[focusedPart as keyof typeof LOCAL_DETAIL_PROFILES];

  return (
    <motion.div data-motion="detail" {...detailMotion} className="project-detail-page mini-detail-page local-preference-page" role="dialog" aria-modal="true" aria-labelledby="local-detail-title">
      <header className="mini-detail-nav">
        <button type="button" aria-label="返回项目列表" onClick={onClose}><ArrowLeft size={22} /></button>
        <strong>{displayProjectName(project)}</strong>
        <span>{positionLabel}</span>
      </header>

      <main className="mini-detail-scroll">
        <img className="mini-detail-hero" src={projectImage(project)} alt="局部推拿服务" />
        <section className="mini-detail-card mini-detail-summary-card">
          <div className="mini-detail-title-row"><h1 id="local-detail-title">{focusedPart}调理</h1></div>
          <DetailIntroduction name={`${focusedPart}调理`} summary="选择本次要做的部位，可多选，按部位计费。" highlights={[activeProfile.focus]} facts={project.duration_min ? [`${project.duration_min}分钟/项`] : [project.price_label || '按次服务']} />
          <DetailPrice current={effectivePrice(project, isMember)} comparison={priceOf(project, isMember ? 'store' : 'member')} isMember={isMember} unit="每个部位" />
        </section>

        {<section className="mini-seat-reminder"><span>服务位置</span><strong>{positionLabel}</strong>{!unseated && <small>请确认位置无误</small>}</section>}

        <section className="mini-config-card">
          <div className="mini-config-title"><strong>选择调理部位</strong><span>可多选 · 按部位计价</span></div>
          <div className="local-part-choice-grid horizontal-switcher">
            {LOCAL_PARTS.map((part) => <button key={part} type="button" disabled={readOnly} className={`${draft.includes(part) ? 'active' : ''} ${focusedPart === part ? 'focused' : ''}`} onClick={() => toggle(part)}><strong>{part}</strong><small>{LOCAL_DETAIL_PROFILES[part].focus}</small></button>)}
          </div>
          {draft.length > 0 && project.duration_min && <p className="mini-seat-reminder">已选 {draft.length} 个部位，共 {draft.length * project.duration_min} 分钟</p>}
        </section>
        {technicianPicker}
      </main>

      <footer className="mini-detail-footer">
        <div className="mini-detail-total"><span>预计合计</span><strong>{formatMoney(total)}</strong></div>
        <div className="mini-detail-actions"><button className="primary" type="button" disabled={readOnly || draft.length === 0} onClick={() => onConfirm(draft)}>{readOnly ? '已提交前台' : unseated ? '加入选单' : '加入本次服务'}<ChevronRight size={17} /></button></div>
      </footer>
    </motion.div>
  );
}
