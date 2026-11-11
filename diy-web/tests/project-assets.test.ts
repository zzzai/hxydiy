import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import { canonicalProjectCode, projectImage, type Project } from '../src/domain.ts';
import { projectDetailVisuals } from '../src/projectDetailVisuals.ts';

const projectRoot = process.cwd();

const VISIBLE_PROJECTS: Array<Pick<Project, 'code' | 'category' | 'name' | 'image_url'>> = [
  { code: 'hxy-xiangxiang-60', category: 'bath', name: '精选草本泡', image_url: '/assets/services/service-foot-bath.jpg' },
  { code: 'hxy-xiaoqi-90', category: 'bath', name: '招牌草本泡', image_url: '/assets/services/service-foot-bath.jpg' },
  { code: 'hxy-nvshen-60', category: 'bath', name: '女神草本泡', image_url: '/assets/services/service-foot-bath.jpg' },
  { code: 'hxy-spa-60', category: 'care', name: '背部舒压SPA', image_url: '/assets/projects/hxy-spa-60.webp' },
  { code: 'hxy-spa-90', category: 'care', name: '舒缓精油SPA', image_url: '/assets/spa-scene.jpg' },
  { code: 'hxy-local-care-60', category: 'local-strength', name: '局部疼痛缓解', image_url: '/diy/assets/service-tuina.jpg' },
  { code: 'hxy-waist-kit-10', category: 'kit', name: '腰臀舒理疗', image_url: '/diy/assets/service-tuina.jpg' },
  { code: 'hxy-neck-kit-10', category: 'kit', name: '肩颈通理疗', image_url: '/diy/assets/service-tuina.jpg' },
  { code: 'hxy-oil-back-30', category: 'local-strength', name: '精油开背', image_url: '/assets/projects/hxy-spa-60.webp' },
  { code: 'hxy-caier-30', category: 'small', name: '采耳', image_url: '/assets/products/daily-care-pack.png' },
  { code: 'hxy-head-30', category: 'small', name: '头疗', image_url: '/assets/products/daily-care-pack.png' },
  { code: 'hxy-jubu-30', category: 'local-strength', name: '局部放松', image_url: '/assets/products/herbal-heat-pack.png' },
  { code: 'hxy-foot-refine-1', category: 'small', name: '足部精修', image_url: '/assets/products/daily-care-pack.png' },
  { code: 'hxy-cupping-scraping-1', category: 'small', name: '拔罐/刮痧', image_url: '/assets/hxy-mascot.webp' },
];

function assetFile(url: string): string {
  return path.join(projectRoot, 'public', url.replace(/^\/diy\/assets\//, 'assets/').replace(/^\/assets\//, 'assets/'));
}

test('顾客菜单所有可见项目主图都存在，门店2的 s2- 编码同样覆盖', () => {
  for (const item of VISIBLE_PROJECTS) {
    for (const code of [item.code, `s2-${item.code}`]) {
      const project = { id: 1, ...item, code } as Project;
      const url = projectImage(project);
      assert.equal(fs.existsSync(assetFile(url)), true, `${code} -> ${url}`);
    }
    assert.equal(canonicalProjectCode(`s2-${item.code}`), item.code);
  }
});

test('顾客项目详情使用的图片都存在，且 no-store 编码匹配专属视觉', () => {
  for (const item of VISIBLE_PROJECTS) {
    for (const section of projectDetailVisuals(item.code)) {
      assert.equal(fs.existsSync(assetFile(section.image)), true, `${item.code} -> ${section.image}`);
    }
    assert.deepEqual(
      projectDetailVisuals(`s2-${item.code}`).map((section) => section.image),
      projectDetailVisuals(item.code).map((section) => section.image),
    );
  }
});
