import { ArrowLeft, BadgeCheck, CalendarCheck2, Gift, QrCode } from 'lucide-react';

import { ANNUAL_MEMBERSHIP_BENEFITS } from '../profile';

export type MembershipKind = 'annual' | 'monthly';

/** 会员卡详情页：99 元权益卡 / 499 元泡脚月卡（仅介绍，到店扫码购买）。 */
export default function MembershipDetailPage({ kind, open, onClose }: {
  kind: MembershipKind | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!open || !kind) return null;
  const isAnnual = kind === 'annual';

  return (
    <div className="membership-detail-page" role="dialog" aria-modal="true" aria-labelledby="membership-detail-title">
      <header className="mini-detail-nav">
        <button type="button" aria-label="返回" onClick={onClose}><ArrowLeft size={22} /></button>
        <strong>{isAnnual ? '会员年度权益卡' : '泡脚月卡'}</strong>
        <span />
      </header>

      <main className="mini-detail-scroll membership-detail-scroll">
        <section className={`membership-hero ${isAnnual ? 'annual' : 'monthly'}`}>
          <span className="membership-hero-price"><strong>{isAnnual ? '99' : '499'}</strong><em>元{isAnnual ? '/年' : '/月'}</em></span>
          <div>
            <h1 id="membership-detail-title">{isAnnual ? '会员年度权益卡' : '泡脚月卡'}</h1>
            <p>{isAnnual ? '全年消费享会员价，周二会员日更优惠' : '30 天不限次草本泡脚，仅限本人'}</p>
          </div>
        </section>

        <section className="mini-detail-card membership-benefits">
          <div className="mini-detail-title-row"><h2>卡片权益</h2><BadgeCheck size={20} /></div>
          <ul>
            {isAnnual ? (
              <>
                <li><BadgeCheck size={15} /><span><strong>{ANNUAL_MEMBERSHIP_BENEFITS.standard}</strong><small>项目确认时按当时有效的会员身份冻结会员价。</small></span></li>
                <li><CalendarCheck2 size={15} /><span><strong>每周二会员日</strong><small>{ANNUAL_MEMBERSHIP_BENEFITS.tuesday}。</small></span></li>
                <li><Gift size={15} /><span><strong>开卡赠送一次项目</strong><small>{ANNUAL_MEMBERSHIP_BENEFITS.gift}。</small></span></li>
              </>
            ) : (
              <>
                <li><BadgeCheck size={15} /><span><strong>30 天不限次草本泡脚</strong><small>开卡后 30 天内使用，适合有持续泡脚需求的顾客。</small></span></li>
                <li><CalendarCheck2 size={15} /><span><strong>仅限本人到店使用</strong><small>卡片与手机号绑定，不可转借他人。</small></span></li>
              </>
            )}
          </ul>
        </section>

        <section className="membership-buy-note">
          <QrCode size={18} />
          <div><strong>到店扫码办理</strong><small>门店确认开通后，权益立即生效。</small></div>
        </section>
      </main>

      <footer className="membership-detail-footer">
        <button type="button" onClick={onClose}>返回菜单</button>
      </footer>
    </div>
  );
}
