import type { LearningAssignment, LearningCourse } from './learningModel';
export type DailyFilter = 'pending' | 'coach' | 'retry' | 'overdue' | 'all';
export const latestAttempt=(item:LearningAssignment)=>item.attempts.slice(-1)[0];
export function shanghaiDay(value: string | number = Date.now()){return new Date(new Date(value).getTime()+8*60*60*1000).toISOString().slice(0,10);}
export function isComplete(item:LearningAssignment){if(item.dailyStatus)return item.dailyStatus==='completed';const latest=latestAttempt(item);return !!latest && latest.total>0 && latest.correct===latest.total;}
export function priority(item:LearningAssignment){const latest=latestAttempt(item);return item.dailyStatus==='needs_retry'?0:latest&&!isComplete(item)?1:item.sectionsRead.length&&!isComplete(item)?2:!isComplete(item)?3:4;}
export function orderedLessons(items:LearningAssignment[],courses:LearningCourse[]){return items.filter(item=>courses.some(c=>c.id===item.courseId&&c.version===item.courseVersion)).slice().sort((a,b)=>priority(a)-priority(b)||a.assignedAt.localeCompare(b.assignedAt)||courses.findIndex(c=>c.id===a.courseId)-courses.findIndex(c=>c.id===b.courseId)||a.id.localeCompare(b.id));}
export function progressLabel(item:LearningAssignment){
 if(item.dailyStatus){const label={scheduled:'尚未到学习日期',not_started:'未开始',in_progress:'学习中',ready:'待答题',needs_coaching:'有错题 · 待辅导',needs_retry:'已辅导 · 待复练',completed:'已完成'}[item.dailyStatus];return label+(item.overdue?' · 已逾期':item.completedLate?' · 补学完成':'');}
 const last=latestAttempt(item);return last ? isComplete(item)?'练习全对':String(last.total-last.correct)+' 道错题待复习' : item.sectionsRead.length?'继续学习':'还没开始';
}
export function needsCoaching(item:LearningAssignment){if(item.dailyStatus)return item.dailyStatus==='needs_coaching';return !!latestAttempt(item)&&!isComplete(item);}
export function selectDailyTasks(items:LearningAssignment[],day:string,filter:DailyFilter){
 return items.filter(item=>!!item.dailyPlanId&&(filter==='overdue'?item.overdue&&!isComplete(item):item.learningDate===day&&(
 filter==='all'||filter==='pending'&&!isComplete(item)||filter==='coach'&&needsCoaching(item)||filter==='retry'&&item.dailyStatus==='needs_retry')));
}
export function learningStats(items:LearningAssignment[],day:string,rosterIds:number[]){
 const daily=selectDailyTasks(items,day,'all');
 return {assigned:daily.length,completed:daily.filter(isComplete).length,incomplete:daily.filter(i=>!isComplete(i)).length,
 coaching:daily.filter(needsCoaching).length,retry:daily.filter(i=>i.dailyStatus==='needs_retry').length,
 unassigned:rosterIds.filter(id=>!daily.some(i=>i.staffId===id)).length};
}
