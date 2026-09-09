import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import {
  buildServicePositionConfigurationPayload,
  canManageServicePositionConfiguration,
} from '../src/servicePositionConfiguration.ts';

test('only store managers receive service position configuration capability', () => {
  assert.equal(canManageServicePositionConfiguration('manager'), true);
  assert.equal(canManageServicePositionConfiguration('admin'), true);
  assert.equal(canManageServicePositionConfiguration('staff'), false);
  assert.equal(canManageServicePositionConfiguration('technician'), false);
});

test('configuration payload contains only maintenance note and display order', () => {
  assert.deepEqual(buildServicePositionConfigurationPayload('靠窗插座待检修', 4), {
    maintenance_note: '靠窗插座待检修',
    display_order: 4,
  });
});

test('service position page exposes manager-only configuration without physical resource actions', () => {
  const source = readFileSync(new URL('../src/pages/ServicePositionsPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /updateServicePositionConfiguration/);
  assert.match(source, /维修备注/);
  assert.match(source, /展示顺序/);
  assert.doesNotMatch(source, /confirmPositionDeparture|finishPositionCleaning|安排入座|结账并清洁/);
});
