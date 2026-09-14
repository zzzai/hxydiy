import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('项目、商品和加项表单使用媒体上传控件而非图片地址输入', () => {
  const project = source('components/project-options/ProjectBasicFields.tsx');
  const addon = source('pages/AddonsPage.tsx');
  const product = source('pages/ProductsPage.tsx');
  assert.match(project, /MediaUploadField/);
  assert.match(addon, /MediaUploadField/);
  assert.match(product, /MediaUploadField/);
  assert.doesNotMatch(project, /主图地址/);
  assert.doesNotMatch(addon, /图片地址/);
});

test('媒体上传控件调用门店隔离的上传 API 并支持删除', () => {
  const component = source('components/MediaUploadField.tsx');
  assert.match(component, /uploadMedia\(file, purpose, storeId\)/);
  assert.match(component, /disabled=.*requireStoreId/);
  assert.match(component, /deleteMedia\(/);
  assert.match(source('api.ts'), /client\.post\('\/admin\/media'/);
});

test('媒体上传失败保留原文件并提供同文件重试', () => {
  const component = source('components/MediaUploadField.tsx');
  assert.match(component, /const \[failedFile, setFailedFile\] = useState<File>\(\)/);
  assert.match(component, /setFailedFile\(file\)/);
  assert.match(component, /upload\(failedFile\)/);
  assert.match(component, />重试上传</);
});
