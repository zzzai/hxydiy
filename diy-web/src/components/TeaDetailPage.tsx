import { ArrowLeft, Check, ChevronRight, Coffee } from 'lucide-react';
import { useEffect, useState } from 'react';

import { resolveTeaImage, TEAS, TEA_DETAIL_PROFILES } from '../domain';
import { motion } from 'framer-motion';
import { detailMotion } from '../motionPresets';
import DetailIntroduction from './DetailIntroduction';

type TeaOption = { name: string; note?: string; description?: string; image_url?: string; image?: string };

type Props = {
  open: boolean;
  selectedTea: string | null;
  positionLabel: string;
  readOnly?: boolean;
  onClose: () => void;
  onConfirm: (tea: string) => void;
  teaOptions?: TeaOption[];
};

export default function TeaDetailPage({ open, selectedTea, positionLabel, readOnly = false, onClose, onConfirm, teaOptions }: Props) {
  const options: TeaOption[] = teaOptions?.length ? teaOptions : TEAS.map((item) => ({ ...item, description: TEA_DETAIL_PROFILES[item.name].description }));
  const [draft, setDraft] = useState(selectedTea || options[0].name);

  useEffect(() => {
    if (open) setDraft(selectedTea || options[0].name);
  }, [open, selectedTea, teaOptions]);

  if (!open) return null;
  const activeTea = options.find((item) => item.name === draft) || options[0];
  const fallback = TEA_DETAIL_PROFILES[activeTea.name as keyof typeof TEA_DETAIL_PROFILES];
  const activeProfile = { highlight: activeTea.note || fallback?.highlight || '到店可选', description: activeTea.description || fallback?.description || '实际供应以门店当日准备为准。' };

  return (
    <motion.div data-motion="detail" {...detailMotion} className="project-detail-page mini-detail-page tea-detail-page" role="dialog" aria-modal="true" aria-labelledby="tea-detail-title">
      <header className="mini-detail-nav">
        <button type="button" aria-label="返回项目列表" onClick={onClose}><ArrowLeft size={22} /></button>
        <strong>茶饮详情</strong>
        <span>{positionLabel}</span>
      </header>

      <main className="mini-detail-scroll">
        <div className="tea-detail-hero"><img key={activeTea.name} src={resolveTeaImage(activeTea)} alt={activeTea.name} /></div>
        <section className="mini-detail-card mini-detail-summary-card">
          <div className="mini-detail-title-row"><h1 id="tea-detail-title">{activeTea.name}</h1><Coffee size={22} /></div>
          <DetailIntroduction name={activeTea.name} summary={activeProfile.description} highlights={[activeProfile.highlight]} />
          <div className="tea-free-price"><strong>免费提供</strong><span>本次到店可选一种</span></div>
        </section>

        <section className="mini-seat-reminder"><span>服务位置</span><strong>{positionLabel}</strong><small>请确认位置无误</small></section>

        <section className="mini-config-card tea-choice-card">
          <div className="mini-config-title"><strong>选择当日茶饮</strong><span>任选一种</span></div>
          <div className="tea-flavor-grid horizontal-switcher">
            {options.map((item) => {
              const active = draft === item.name;
              return (
                <button key={item.name} type="button" aria-pressed={active} disabled={readOnly} className={active ? 'active' : ''} onClick={() => setDraft(item.name)}>
                  <img src={resolveTeaImage(item)} alt="" loading="lazy" decoding="async" />
                  <span><strong>{item.name}</strong><small>{item.note}</small></span>
                  {active && <Check size={14} />}
                </button>
              );
            })}
          </div>
          <p className="tea-choice-note">实际供应以门店当日准备为准，茶饮不单独收费。</p>
        </section>
      </main>

      <footer className="mini-detail-footer tea-detail-footer">
        <div className="mini-detail-total"><span>本次茶饮</span><strong>免费</strong></div>
        <div className="mini-detail-actions"><button className="primary" type="button" disabled={readOnly} onClick={() => onConfirm(draft)}>{readOnly ? '已提交前台' : '加入本次服务'}<ChevronRight size={17} /></button></div>
      </footer>
    </motion.div>
  );
}
