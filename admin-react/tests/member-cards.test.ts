import assert from 'node:assert/strict';
import test from 'node:test';
import { explainMemberCard, type MemberCardExplanation } from '../src/memberCards.ts';

const card: MemberCardExplanation = { source: 'test', card_type: 'stored', state: 'exhausted', started_at: '2026-09-01T00:00:00Z', expires_at: null, balance_cents: 0, balance_realtime: false, recorded_at: '2026-09-28T00:00:00Z' };

test('stored card explanation preserves cents and snapshot warning', () => {
  assert.equal(explainMemberCard(card).state, '余额耗尽');
  assert.equal(explainMemberCard({ ...card, balance_cents: 1234 }).balance, '¥12.34（记录时点余额，非实时同步）');
});

test('annual expiry is shown without fabricating a new date or stored balance', () => {
  const result = explainMemberCard({ ...card, card_type: 'annual', state: 'expired', expires_at: '2027-09-01T00:00:00Z' });
  assert.equal(result.state, '已到期');
  assert.equal(result.expiry, '2027-09-01T00:00:00Z');
  assert.equal(result.balance, '不作为储值余额');
});
