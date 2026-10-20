import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ADMIN_STAFF_KEY,
  ADMIN_TOKEN_KEY,
  TECHNICIAN_STAFF_KEY,
  TECHNICIAN_TOKEN_KEY,
  activeSessionSlot,
  clearActiveStaffSession,
  migrateLegacyTechnicianSession,
  readActiveStaff,
  readActiveToken,
  writeStaffSession,
} from '../src/staffSession.ts';

function memory() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

test('opening admin moves a leftover technician login out of the admin slot', () => {
  const storage = memory();
  storage.setItem(ADMIN_TOKEN_KEY, 'tech-token');
  storage.setItem(ADMIN_STAFF_KEY, JSON.stringify({ role: 'technician', name: '技师甲' }));
  assert.equal(migrateLegacyTechnicianSession(storage), true);
  assert.equal(readActiveToken(storage, '/admin/'), '');
  assert.equal(readActiveStaff(storage, '/admin/'), null);
  assert.equal(storage.getItem(TECHNICIAN_TOKEN_KEY), 'tech-token');
  assert.equal(JSON.parse(storage.getItem(TECHNICIAN_STAFF_KEY) || 'null').name, '技师甲');
  assert.equal(storage.getItem(ADMIN_TOKEN_KEY), null);
});

test('admin and technician sessions stay signed in at the same time', () => {
  const storage = memory();
  writeStaffSession(storage, { token: 'manager-token', staff: { role: 'manager', name: '店长' } });
  writeStaffSession(storage, { token: 'tech-token', staff: { role: 'technician', name: '技师甲' } });
  assert.equal(readActiveToken(storage, '/admin/'), 'manager-token');
  assert.equal(readActiveStaff(storage, '/admin/')?.role, 'manager');
  assert.equal(readActiveToken(storage, '/technician/today'), 'tech-token');
  assert.equal(readActiveStaff(storage, '/technician/today')?.role, 'technician');
  clearActiveStaffSession(storage, '/admin/');
  assert.equal(readActiveToken(storage, '/admin/'), '');
  assert.equal(readActiveToken(storage, '/technician/today'), 'tech-token');
  clearActiveStaffSession(storage, '/technician/today');
  assert.equal(storage.getItem(ADMIN_TOKEN_KEY), null);
  assert.equal(readActiveToken(storage, '/technician/today'), '');
});

test('a manager using the technician entry keeps the admin slot', () => {
  const storage = memory();
  writeStaffSession(storage, { token: 'manager-token', staff: { role: 'manager' } });
  assert.equal(activeSessionSlot(storage, '/technician/member-verify'), 'admin');
  assert.equal(readActiveToken(storage, '/technician/member-verify'), 'manager-token');
});
