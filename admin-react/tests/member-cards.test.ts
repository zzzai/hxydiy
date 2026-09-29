import assert from 'node:assert/strict';
import test from 'node:test';
import { explainMemberCard, type MemberCardExplanation } from '../src/memberCards.ts';

const card: MemberCardExplanation = { source: 'test', card_type: 'stored', state: 'exhausted', started_at: '2026-09-01T00:00:00Z', expires_at: null, balance_cents: 0, balance_realtime: false, recorded_at: '2026-09-28T00:00:00Z' };

test('stored card explanation does not expose the retained balance', () => {
  assert.equal(explainMemberCard(card).state, '余额耗尽');
  const result = explainMemberCard({ ...card, balance_cents: 1234 });
  assert.equal('balance' in result, false);
  assert.equal(JSON.stringify(result).includes('12.34'), false);
});

test('annual expiry is shown without fabricating a new date or stored balance', () => {
  const result = explainMemberCard({ ...card, card_type: 'annual', state: 'expired', expires_at: '2027-09-01T00:00:00Z' });
  assert.equal(result.state, '已到期');
  assert.equal(result.expiry, '2027-09-01T00:00:00Z');
  assert.equal('balance' in result, false);
});
