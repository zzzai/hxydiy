import assert from 'node:assert/strict';
import test from 'node:test';
import * as entry from '../src/returnEntry.ts';

test('service-account menu links open the unseated hub, not arrival sessions', () => {
  assert.equal(typeof entry.isServiceAccountEntry, 'function');
  for (const query of ['store=1&view=menu', 'store=1&view=menu&source=service_account', 'view=menu&source=store_qr', 'view=menu&page=projects', 'view=menu&page=seats']) {
    assert.equal(entry.isServiceAccountEntry(new URLSearchParams(query)), true, query);
  }
  for (const query of ['store=1', 'view=return', 'view=menu&seat=sofa-03', 'view=menu&qr=signed', 'view=menu&session=bound&token=secret', 'view=menu&project=hxy-qiqing-30', 'view=menu&source=kiosk']) {
    assert.equal(entry.isServiceAccountEntry(new URLSearchParams(query)), false, query);
  }
});

test('public navigation never carries visit or report credentials', () => {
  assert.equal(typeof entry.serviceAccountEntry, 'function');
  const origin = 'https://diy.hexiaoyue.com/?seat=sofa-03&session=old&token=secret#report';
  assert.equal(entry.serviceAccountEntry(origin, 1), 'https://diy.hexiaoyue.com/?store=1&view=menu');
  assert.equal(entry.serviceAccountEntry(origin, 1, 'projects'), 'https://diy.hexiaoyue.com/?store=1&view=menu&page=projects');
  assert.equal(entry.serviceAccountEntry(origin, -1, 'seats'), 'https://diy.hexiaoyue.com/?store=1&view=menu&page=seats');
});
