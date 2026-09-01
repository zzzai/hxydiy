import assert from 'node:assert/strict';
import test from 'node:test';

import { createDiyPageTracking } from '../src/pageTracking.ts';

test('页面关键行为使用稳定事件名并携带可分析字段', () => {
  const events: Array<{ event: string; data: Record<string, unknown> }> = [];
  const tracking = createDiyPageTracking((event, data) => events.push({ event, data }));

  tracking.entryView({ entry_state: 'ready' });
  tracking.projectView({ project_id: 12, project_code: 'P-12', project_name: '肩颈调理' });
  tracking.projectConfigSave({ project_id: 12, preference_count: 2, addon_count: 1 });
  tracking.loginPromptView({ prompt_type: 'record', trigger: 'feedback' });
  tracking.feedbackView({ can_evaluate: true });
  tracking.navigationBack({ overlay: 'project-detail', method: 'edge_swipe' });

  assert.deepEqual(events, [
    { event: 'diy_entry_view', data: { entry_state: 'ready' } },
    { event: 'project_view', data: { project_id: 12, project_code: 'P-12', project_name: '肩颈调理' } },
    { event: 'project_config_save', data: { project_id: 12, preference_count: 2, addon_count: 1 } },
    { event: 'login_prompt_view', data: { prompt_type: 'record', trigger: 'feedback' } },
    { event: 'feedback_view', data: { can_evaluate: true } },
    { event: 'navigation_back', data: { overlay: 'project-detail', method: 'edge_swipe' } },
  ]);
});
