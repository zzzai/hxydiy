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

test('足部精修和女神项目图片同时存在于源码素材与生产构建产物', () => {
  const normalizeAsset = (asset: string | undefined) => asset?.replace(/^\/(?:diy\/)?/, '');
  const mainAsset = normalizeAsset(projectImage(footRefine));
  const detailAsset = normalizeAsset(projectDetailVisuals(footRefine.code)[0]?.image);

  assert.equal(mainAsset, 'assets/projects/hxy-foot-refine-1.webp');
  assert.equal(detailAsset, 'assets/projects/hxy-foot-refine-1-detail.webp');

  const goddess = { ...footRefine, code: 'hxy-nvshen-60', name: '草本足护-女神专享' } as Project;
  const goddessMain = normalizeAsset(projectImage(goddess));
  const goddessDetail = normalizeAsset(projectDetailVisuals(goddess.code)[0]?.image);
  assert.equal(goddessMain, 'assets/projects/hxy-nvshen-60.webp');
  assert.equal(goddessDetail, 'assets/projects/hxy-nvshen-60-detail.webp');

  for (const asset of [mainAsset, detailAsset, goddessMain, goddessDetail]) {
    assert.ok(asset, '足部精修详情必须配置图片');
    const sourcePath = path.join(projectRoot, 'public', asset);
    const builtPath = path.join(projectRoot, 'dist', asset);
    assert.equal(fs.existsSync(sourcePath), true, `public 缺少 ${asset}`);
    assert.equal(fs.existsSync(builtPath), true, `dist 缺少 ${asset}`);
    const sourceBytes = fs.readFileSync(sourcePath);
    const builtBytes = fs.readFileSync(builtPath);
    for (const [location, bytes] of [['public', sourceBytes], ['dist', builtBytes]] as const) {
      assert.equal(bytes.subarray(0, 4).toString('ascii'), 'RIFF', `${location}/${asset} 不是 RIFF 图片`);
      assert.equal(bytes.subarray(8, 12).toString('ascii'), 'WEBP', `${location}/${asset} 不是 WebP 图片`);
    }
    assert.deepEqual(builtBytes, sourceBytes, `dist/${asset} 与 public 源素材不一致，请重新构建`);
  }

  const mainBytes = fs.readFileSync(path.join(projectRoot, 'public', mainAsset));
  const detailBytes = fs.readFileSync(path.join(projectRoot, 'public', detailAsset));
  assert.notDeepEqual(mainBytes, detailBytes, '菜单主图和详情长图不能复用同一张图片');
});
