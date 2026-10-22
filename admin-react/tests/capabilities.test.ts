import assert from 'node:assert/strict';
import test from 'node:test';
import { capabilitiesFor, hasCapability } from '../src/core/auth/capabilities.ts';

test('manager capabilities match the operation-level matrix', () => {
  assert.equal(hasCapability('manager', 'view_store_operations', 1, 2), true);
  assert.equal(hasCapability('manager', 'toggle_catalog_publication', 1, 2), true);
  assert.equal(hasCapability('manager', 'follow_up_reviews', 1, 2), true);
  assert.equal(hasCapability('manager', 'manage_catalog_master', 1, 2), false);
  assert.equal(hasCapability('manager', 'manage_staff_accounts', 1, 2), false);
  assert.equal(hasCapability('manager', 'manage_headquarters', 1, 2), false);
});

test('technician and read-only staff are fail-closed', () => {
  assert.equal(hasCapability('technician', 'self_service', 1, 2), true);
  assert.equal(hasCapability('technician', 'view_store_operations', 1, 2), false);
  assert.equal(hasCapability('staff', 'view_store_operations', 1), true);
  assert.equal(hasCapability('staff', 'toggle_catalog_publication', 1), false);
  assert.deepEqual(capabilitiesFor('unknown'), Object.fromEntries(Object.keys(capabilitiesFor('unknown')).map(key => [key, false])));
});

test('headquarters admin gets all capabilities except self service', () => {
  const capabilities = capabilitiesFor('admin', null);
  assert.equal(capabilities.manage_headquarters, true);
  assert.equal(capabilities.manage_catalog_master, true);
  assert.equal(capabilities.self_service, false);
});

test('store-scoped admin keeps brand content management within its scope', () => {
  const capabilities = capabilitiesFor('admin', 1);
  assert.equal(capabilities.manage_catalog_master, true);
  assert.equal(capabilities.manage_marketing, true);
  assert.equal(capabilities.manage_automation, true);
  assert.equal(capabilities.manage_headquarters, false);
  assert.equal(capabilities.self_service, false);
});
