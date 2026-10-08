import { ArrowLeft, BadgeCheck, CalendarCheck2, Gift, MessageSquareText } from 'lucide-react';

import { ANNUAL_MEMBERSHIP_BENEFITS, MEMBERSHIP_PLANS, MEMBERSHIP_STORE_CONFIRMATION, STORED_MEMBERSHIP_TEA } from '../profile';

export type MembershipKind = 'annual' | 'stored';

/** Card introduction only; no purchase, gift allocation or eligibility mutation. */
export default function MembershipDetailPage({ kind, open, onClose }: {
  kind: MembershipKind | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!open || !kind) return null;
  const isAnnual = kind === 'annual';
  const plan = MEMBERSHIP_PLANS[kind];

  return (
    <div className="membership-detail-page" role="dialog" aria-modal="true" aria-labelledby="membership-detail-title">
      <header className="mini-detail-nav">
        <button type="button" aria-label="返回" onClick={onClose}><ArrowLeft size={22} /></button>
        <strong>{plan.name}</strong>
        <span />
      </header>

      <main className="mini-detail-scroll membership-detail-scroll">
        <section className={`membership-hero ${isAnnual ? 'annual' : 'monthly'}`}>
          <span className="membership-hero-price"><strong>{plan.price}</strong><em>{plan.unit}</em></span>
          <div>
            <h1 id="membership-detail-title">{plan.name}</h1>
            <p>{plan.summary}</p>
          </div>
        </section>

        <section className="mini-detail-card membership-benefits">
          <div className="mini-detail-title-row"><h2>卡片权益</h2><BadgeCheck size={20} /></div>
          <ul>
            <li><BadgeCheck size={15} /><span><strong>{ANNUAL_MEMBERSHIP_BENEFITS.standard}</strong><small>{plan.validity}。</small></span></li>
            <li><CalendarCheck2 size={15} /><span><strong>每周二会员日</strong><small>{ANNUAL_MEMBERSHIP_BENEFITS.tuesday}。</small></span></li>
            <li><Gift size={15} /><span><strong>开卡赠送一次项目</strong><small>{ANNUAL_MEMBERSHIP_BENEFITS.gift}。</small></span></li>
            {!isAnnual && <li><Gift size={15} /><span><strong>开卡另赠养生茶</strong><small>{STORED_MEMBERSHIP_TEA}。</small></span></li>}
          </ul>
        </section>

        <section className="membership-buy-note">
          <MessageSquareText size={18} />
          <div><strong>到店联系前台办理</strong><small>{MEMBERSHIP_STORE_CONFIRMATION}</small></div>
        </section>
      </main>

      <footer className="membership-detail-footer">
        <button type="button" onClick={onClose}>返回菜单</button>
      </footer>
    </div>
  );
}
