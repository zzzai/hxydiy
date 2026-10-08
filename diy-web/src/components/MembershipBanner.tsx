import { BadgeCheck, CalendarCheck2, Gift, MessageSquareText } from 'lucide-react';

import { ANNUAL_MEMBERSHIP_BENEFITS, MEMBERSHIP_PLANS, MEMBERSHIP_STORE_CONFIRMATION, STORED_MEMBERSHIP_TEA } from '../profile';

/** Membership introduction only; store staff confirm activation and gifts. */
export default function MembershipBanner() {
  return (
    <section className="membership-banner" id="membership-banner" aria-label="会员方案">
      <div className="membership-cards">
        <article className="membership-card primary">
          <div className="membership-card-head">
            <span className="membership-price"><strong>99</strong><em>元/年</em></span>
            <span className="membership-tag">年度权益</span>
          </div>
          <h2>{MEMBERSHIP_PLANS.annual.name}</h2>
          <ul>
            <li><BadgeCheck size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.standard}</li>
            <li><CalendarCheck2 size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.tuesday}</li>
            <li><Gift size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.gift}</li>
          </ul>
        </article>

        <article className="membership-card">
          <div className="membership-card-head">
            <span className="membership-price"><strong>{MEMBERSHIP_PLANS.stored.price}</strong><em>{MEMBERSHIP_PLANS.stored.unit}</em></span>
          </div>
          <h2>{MEMBERSHIP_PLANS.stored.name}</h2>
          <ul>
            <li><BadgeCheck size={14} />{MEMBERSHIP_PLANS.stored.validity}</li>
            <li><BadgeCheck size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.standard}</li>
            <li><CalendarCheck2 size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.tuesday}</li>
            <li><Gift size={14} />{ANNUAL_MEMBERSHIP_BENEFITS.gift}</li>
            <li><Gift size={14} />{STORED_MEMBERSHIP_TEA}</li>
          </ul>
        </article>
      </div>
      <p className="membership-note"><MessageSquareText size={13} />{MEMBERSHIP_STORE_CONFIRMATION}</p>
    </section>
  );
}
