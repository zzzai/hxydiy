import type { components } from './generated/openapi';

export type MemberCardExplanation = components['schemas']['MemberCardExplanation'];
export type MembershipExplanation = components['schemas']['MembershipExplanation'];

export function explainMemberCard(card: MemberCardExplanation) {
  const states = { active: '有效', disabled: '已停用', scheduled: '尚未生效', expired: '已到期', invalid: '资料待核实', exhausted: '余额耗尽' };
  return {
    kind: card.card_type === 'annual' ? '年度权益卡' : '储值权益卡',
    state: states[card.state],
    balance: card.card_type === 'stored' ? `¥${(card.balance_cents / 100).toFixed(2)}（记录时点余额，非实时同步）` : '不作为储值余额',
    expiry: card.expires_at || '未记录到期日，按余额判定',
  };
}
