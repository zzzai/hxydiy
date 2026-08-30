import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import { projectImage, type Project } from '../src/domain.ts';
import { projectDetailVisuals } from '../src/projectDetailVisuals.ts';

const projectRoot = process.cwd();
const footRefine = {
  id: 14,
  code: 'hxy-foot-refine-1',
  category: 'small',
  name: '足部精修',
  image_url: '',
  summary: '',
  duration_min: 0,
  publication_status: 'published',
  tags: [],
  prices: [],
} as unknown as Project;

test('足部精修主图和详情图同时存在于源码素材与生产构建产物', () => {
  const normalizeAsset = (asset: string | undefined) => asset?.replace(/^\/(?:diy\/)?/, '');
  const mainAsset = normalizeAsset(projectImage(footRefine));
  const detailAsset = normalizeAsset(projectDetailVisuals(footRefine.code)[0]?.image);

  assert.equal(mainAsset, 'assets/projects/hxy-foot-refine-1.webp');
  assert.equal(detailAsset, 'assets/projects/hxy-foot-refinement-1.webp');

  for (const asset of [mainAsset, detailAsset]) {
    assert.ok(asset, '足部精修详情必须配置图片');
    assert.equal(fs.existsSync(path.join(projectRoot, 'public', asset)), true, `public 缺少 ${asset}`);
    assert.equal(fs.existsSync(path.join(projectRoot, 'dist', asset)), true, `dist 缺少 ${asset}`);
  }
});
