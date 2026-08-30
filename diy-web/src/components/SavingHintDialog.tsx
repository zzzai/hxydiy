import { ChevronRight, TicketPercent, X } from 'lucide-react';

import type { SavingHint } from '../api';
import { formatMoney } from '../domain';

type Props = {
  hint: SavingHint | null;
  open: boolean;
  onLogin: () => void;
  onSkip: () => void;
};

export default function SavingHintDialog({ hint, open, onLogin, onSkip }: Props) {
  if (!open || !hint) return null;
  const member = hint.kind === 'member';
  return (
    <div className="saving-hint-overlay" role="dialog" aria-modal="true" aria-labelledby="saving-hint-title">
      <section className="saving-hint-dialog">
        <button className="saving-hint-close" type="button" aria-label="关闭" onClick={onSkip}><X size={18} /></button>
        <div className="saving-hint-icon">{member ? '省' : <TicketPercent size={22} />}</div>
        <p className="eyebrow">荷小悦到店礼遇</p>
        <h2 id="saving-hint-title">{member ? `登录识别会员身份，预计可省 ${formatMoney(hint.estimated_saving_cents || 0)}` : '登录领取到店礼，符合条件后预计自动抵扣'}</h2>
        <p className="saving-hint-copy">不登录也可提交，服务完成后统一线下结算，最终以门店确认的服务清单为准。</p>
        <button className="saving-hint-primary" type="button" onClick={onLogin}>{member ? '登录查看会员价' : '登录领取到店礼'}<ChevronRight size={17} /></button>
        <button className="saving-hint-skip" type="button" onClick={onSkip}>暂不登录</button>
      </section>
    </div>
  );
}
