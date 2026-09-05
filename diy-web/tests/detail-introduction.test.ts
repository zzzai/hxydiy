import assert from 'node:assert/strict';
import test from 'node:test';
import { detailIntroduction } from '../src/detailIntroduction.ts';

test('详情介绍保留原文并去除已表达的特色和无决策价值规则', () => {
  const result = detailIntroduction({ name: '足部精修', summary: '现煮草本泡脚+脚底精修', highlights: ['现煮草本', '脚底精修'], facts: ['单次服务', '可搭配局部加强'] });
  assert.equal(result.summary, '现煮草本泡脚 · 脚底精修');
  assert.deepEqual(result.highlights, []);
  assert.deepEqual(result.facts, []);
});

test('套盒次数和分段服务时长保留，避免精简导致规格丢失', () => {
  const kit = detailIntroduction({ name: '套盒项目', summary: '工具调理', highlights: [], facts: ['10次/套', '套盒服务', '单次服务'] });
  assert.deepEqual(kit.facts, ['10次/套', '套盒服务']);
  const spa = detailIntroduction({ name: '精油护理', summary: '头部按摩', highlights: ['头部按摩'], duration: 60, facts: ['45+15分钟分段服务'] });
  assert.deepEqual(spa.facts, ['60分钟', '45+15分钟分段服务']);
});

test('已有时长不重复，未知或零时长不虚构服务分钟数', () => {
  assert.deepEqual(detailIntroduction({ name: '采耳', summary: '30分钟服务', highlights: [], duration: 30 }).facts, []);
  assert.deepEqual(detailIntroduction({ name: '项目', summary: '说明', highlights: [], duration: 0 }).facts, []);
});

test('局部服务保留每项单位，特色最多两项且去重', () => {
  const result = detailIntroduction({ name: '腰部调理', summary: '服务说明', highlights: ['局部放松', '局部放松', '草本热敷', '其他'], facts: ['30分钟/项'] });
  assert.deepEqual(result.highlights, ['局部放松', '草本热敷']);
  assert.deepEqual(result.facts, ['30分钟/项']);
});
