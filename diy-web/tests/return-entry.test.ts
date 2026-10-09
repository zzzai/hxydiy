import assert from 'node:assert/strict';
import test from 'node:test';
import { isReturnEntry, returnBannerKey, safeStoreContact, stableStoreEntry, STORE_CONTACTS } from '../src/returnEntry.ts';

test('fixed return links contain only store and return mode, never visit credentials', () => {
  const url = new URL(stableStoreEntry('https://diy.hexiaoyue.com/?seat=sofa-01&token=secret#report', 1));
  assert.equal(url.pathname, '/');
  assert.deepEqual([...url.searchParams], [['store', '1'], ['view', 'return']]);
  assert.equal(url.hash, '');
  assert.equal(new URL(stableStoreEntry('https://diy.hexiaoyue.com', -1)).searchParams.get('store'), '1');
});

test('return mode bypasses stale seat context; explicit arrival and kiosk flows remain unchanged', () => {
  assert.equal(isReturnEntry(new URLSearchParams('store=1')), true);
  assert.equal(isReturnEntry(new URLSearchParams('store=1&view=return&seat=occupied&session=old&token=old')), true);
  for (const query of ['seat=sofa-01', 'qr=signed', 'session=old', 'project=hxy-qiqing-30', 'view=menu', 'source=kiosk']) assert.equal(isReturnEntry(new URLSearchParams(query)), false);
});

test('official store contact is isolated by store and rejects unapproved sources', () => {
  assert.equal(safeStoreContact(STORE_CONTACTS[1])?.addUrl, 'https://work.weixin.qq.com/u/vcd649012bd26ad232?v=5.0.10.79677&bb=fcec4c6148');
  assert.equal(safeStoreContact(STORE_CONTACTS[2]), null);
  assert.equal(safeStoreContact({ name: 'Store', addUrl: 'https://work.weixin.qq.com/ca/confirmed' })?.addUrl, 'https://work.weixin.qq.com/ca/confirmed');
  for (const addUrl of ['https://evil.example/ca/confirmed', 'https://work.weixin.qq.com:443/ca/confirmed', 'https://work.weixin.qq.com/ca/confirmed?redirect=evil', 'https://work.weixin.qq.com/u/id?v=1.0&v=2.0', 'javascript:alert(1)']) assert.equal(safeStoreContact({ name: 'Store', addUrl }), null);
  assert.equal(safeStoreContact({ name: 'Store', qrImage: '/assets/store-contact/../login.png' }), null);
  assert.notEqual(returnBannerKey(1), returnBannerKey(2));
});
