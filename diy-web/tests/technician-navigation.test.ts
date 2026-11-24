import test from 'node:test';
import assert from 'node:assert/strict';
import { createOverlayHistoryState } from '../src/overlayHistory.ts';
import { readTechnicianView, technicianBackSteps, technicianViewState } from '../src/technicianNavigation.ts';

test('browsing, changing people and opening a photo preserve the editing portion under the directory', () => {
  const editor = createOverlayHistoryState({}, 'project-detail');
  const origin = {storeId: 2, projectId: 22};
  const list = technicianViewState(editor, origin);
  const first = technicianViewState(list, {...origin, profile: 'number-1'});
  const second = technicianViewState(first, {...origin, profile: 'number-09'}, true);
  const photo = technicianViewState(second, {...origin, profile: 'number-09', photo: 0});
  assert.deepEqual(readTechnicianView(list, 2), origin);
  assert.equal(readTechnicianView(second, 2)?.profile, 'number-09');
  assert.equal(readTechnicianView(photo, 2)?.photo, 0);
  assert.equal(technicianBackSteps(photo), 3);
  assert.equal(technicianBackSteps(second), 2);
  assert.equal(technicianBackSteps(editor), 0);
});

test('another store and a project opened over the directory do not render the previous profile', () => {
  const list = technicianViewState(null, {storeId: 1});
  const person = technicianViewState(list, {storeId: 1, profile: 'staff-6'});
  const project = createOverlayHistoryState(person, 'project-detail');
  assert.equal(readTechnicianView(person, 2), null);
  assert.equal(readTechnicianView(project, 1), null);
  assert.equal(technicianBackSteps(project), 0);
  assert.equal(readTechnicianView(person, 1)?.profile, 'staff-6');
});
