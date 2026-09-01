import { BadgeCheck, CalendarCheck2, Gift, QrCode } from 'lucide-react';

import { ANNUAL_MEMBERSHIP_BENEFITS } from '../profile';

/** 首页顶部会员方案展示区：99 元权益卡 + 泡脚月卡，仅作介绍，到店扫码购买。 */
export default function MembershipBanner() {
  return (
    <section className="membership-banner" id="membership-banner" aria-label="会员方案">
      <div className="membership-cards">
        <article className="membership-card primary">
          <div className="membership-card-head">
            <span className="membership-price"><strong>99</strong><em>元/年</em></span>
            <span className="membership-tag">年度权益</span>
          </div>
          <h2>会员年度权益卡</h2>
          <ul>
            <li><BadgeCheck size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.standard}</li>
            <li><CalendarCheck2 size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.tuesday}</li>
            <li><Gift size={14} />开卡赠送一次，门店价 99 元以下项目任选一项</li>
          </ul>
        </article>

        <article className="membership-card">
          <div className="membership-card-head">
            <span className="membership-price"><strong>499</strong><em>元/月</em></span>
          </div>
          <h2>泡脚月卡</h2>
          <ul>
            <li><BadgeCheck size={14} />30 天不限次草本泡脚</li>
            <li><CalendarCheck2 size={14} />仅限本人到店使用</li>
          </ul>
        </article>
      </div>
      <p className="membership-note"><QrCode size={13} />到店扫码办理，门店确认开通后即可使用。</p>
    </section>
  );
}
