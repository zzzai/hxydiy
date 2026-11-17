import test from 'node:test';
import assert from 'node:assert/strict';
import { isComplete, selectDailyTasks, learningStats, progressLabel, shanghaiDay } from '../src/technician/learning/dailyLearningModel.ts';
import type { LearningAssignment } from '../src/technician/learning/learningModel.ts';

function task(id:string, status:LearningAssignment['dailyStatus'], day='2026-11-17'):LearningAssignment {
 return {id,assignmentId:'base',dailyPlanId:id,learningDate:day,dailyStatus:status,overdue:false,completedLate:false,storeId:1,staffId:2,staffName:'Synthetic',courseId:'one',courseVersion:'1',assignedAt:'2026-11-17T00:00:00Z',dueAt:'2026-11-17T15:59:00Z',revision:1,sectionsRead:[],attempts:[],followUps:[]};
}
test('daily status is authoritative over old perfect answers',()=>{
 const retry={...task('r','needs_retry'),attempts:[{id:'old',answers:{},correct:3,total:3,createdAt:''}]};
 assert.equal(isComplete(retry),false);
 assert.equal(progressLabel(retry),'已辅导 · 待复练');
 assert.equal(isComplete(task('c','completed')),true);
});
test('selected date counts tasks and unique staff separately',()=>{
 const values=[task('a','not_started'),task('b','completed'),task('tomorrow','scheduled','2026-11-18')];
 const stats=learningStats(values,'2026-11-17',[2,3]);
 assert.deepEqual(stats,{assigned:2,completed:1,incomplete:1,coaching:0,retry:0,unassigned:1});
 assert.equal(selectDailyTasks(values,'2026-11-17','pending').length,1);
 assert.equal(selectDailyTasks(values,'2026-11-17','all').length,2);
});
test('overdue spans dates while legacy stays outside daily metrics',()=>{
 const late={...task('late','needs_retry','2026-11-16'),overdue:true};
 const legacy={...task('legacy',undefined),dailyPlanId:undefined,learningDate:undefined};
 assert.deepEqual(selectDailyTasks([late,legacy],'2026-11-17','overdue').map(t=>t.id),['late']);
 assert.equal(learningStats([late,legacy],'2026-11-17',[]).assigned,0);
});
test('Beijing midnight is independent of the device timezone',()=>{
 assert.equal(shanghaiDay('2026-11-17T15:59:00Z'),'2026-11-17');
 assert.equal(shanghaiDay('2026-11-17T16:01:00Z'),'2026-11-18');
});
