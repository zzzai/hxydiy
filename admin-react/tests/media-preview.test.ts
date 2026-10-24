import test from 'node:test';
import assert from 'node:assert/strict';
import { mediaPreviewSource } from '../src/mediaPreview.ts';
test('public catalog assets use the customer asset root without API credentials', () => {
  assert.deepEqual(mediaPreviewSource('/assets/services/service-foot-bath.jpg'), { authenticated: false, url: '/diy/assets/services/service-foot-bath.jpg' });
  assert.deepEqual(mediaPreviewSource('assets/a.jpg'), { authenticated: false, url: '/diy/assets/a.jpg' });
  assert.deepEqual(mediaPreviewSource('/diy/assets/a.jpg'), { authenticated: false, url: '/diy/assets/a.jpg' });
});
test('protected media keeps authentication and avoids duplicating the API prefix', () => {
  assert.deepEqual(mediaPreviewSource('/api/v1/admin/media/23/content'), { authenticated: true, url: '/admin/media/23/content' });
  assert.deepEqual(mediaPreviewSource('/admin/media/23/content'), { authenticated: true, url: '/admin/media/23/content' });
});
test('external images do not receive the API authorization header', () => {
  assert.deepEqual(mediaPreviewSource('https://example.test/a.jpg'), { authenticated: false, url: 'https://example.test/a.jpg' });
  assert.equal(mediaPreviewSource(), undefined);
});
