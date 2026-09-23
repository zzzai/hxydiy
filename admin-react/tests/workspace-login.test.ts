import assert from 'node:assert/strict';
import test from 'node:test';

import {
  finishWorkspaceSelection,
  interpretStaffLogin,
  storeStaffSession,
  type StaffLoginResponse,
} from '../src/workspaceLogin.ts';

const brand = { assignment_id: 1, role: 'brand_admin' as const, scope_type: 'brand' as const, scope_id: null, scope_name: '荷小悦品牌总部' };
const store = { assignment_id: 4, role: 'store_manager' as const, scope_type: 'store' as const, scope_id: 1, scope_name: '紫薇壹号店' };
const headquartersStaff = { id: 1, name: 'Administrator', role: 'admin', store_id: null, technician_id: null, store_name: '' };
const storeStaff = { ...headquartersStaff, role: 'manager', store_id: 1, store_name: '紫薇壹号店' };
const brandScopedStaff = { ...headquartersStaff, role: 'brand_admin' };
const storeScopedStaff = { ...storeStaff, role: 'store_manager' };

test('two workspaces require an explicit selection before a usable staff session exists', () => {
  const response: StaffLoginResponse = { token: 'selector-token', selector_token: 'selector-token', workspaces: [brand, store], staff: headquartersStaff };
  assert.deepEqual(interpretStaffLogin(response), { kind: 'select', selectorToken: 'selector-token', workspaces: [brand, store] });
});

test('one workspace and technician logins keep their existing direct-entry behavior', () => {
  assert.deepEqual(interpretStaffLogin({ token: 'scoped-token', selector_token: 'selector-token', workspaces: [brand], staff: brandScopedStaff }), {
    kind: 'ready', token: 'scoped-token', staff: headquartersStaff,
  });
  assert.deepEqual(interpretStaffLogin({ token: 'tech-token', selector_token: null, workspaces: [], staff: { ...storeStaff, role: 'technician', technician_id: 8 } }), {
    kind: 'ready', token: 'tech-token', staff: { ...storeStaff, role: 'technician', technician_id: 8 },
  });
});

test('selected store workspace saves only the scoped token and its store context', () => {
  const ready = finishWorkspaceSelection({ token: 'store-scoped-token', workspace: store, staff: storeScopedStaff }, store.assignment_id);
  const values = new Map<string, string>();
  const storage = { setItem: (key: string, value: string) => { values.set(key, value); } };
  storeStaffSession(storage, ready);
  assert.equal(values.get('hxy_admin_token'), 'store-scoped-token');
  assert.deepEqual(JSON.parse(values.get('hxy_admin_staff') || 'null'), storeStaff);
  assert.equal([...values.values()].includes('selector-token'), false);
});

test('selected brand workspace preserves admin navigation role', () => {
  const ready = finishWorkspaceSelection({ token: 'brand-scoped-token', workspace: brand, staff: brandScopedStaff }, brand.assignment_id);
  assert.deepEqual(ready.staff, headquartersStaff);
});

test('mismatched workspace response cannot be stored as the requested store', () => {
  assert.throws(
    () => finishWorkspaceSelection({ token: 'brand-token', workspace: brand, staff: headquartersStaff }, store.assignment_id),
    /工作区/,
  );
});

test('selected workspace rejects an inconsistent staff scope or role', () => {
  assert.throws(
    () => finishWorkspaceSelection({ token: 'store-token', workspace: store, staff: headquartersStaff }, store.assignment_id),
    /工作区/,
  );
  assert.throws(
    () => finishWorkspaceSelection({ token: 'store-token', workspace: store, staff: { ...storeStaff, role: 'staff' } }, store.assignment_id),
    /工作区/,
  );
});
