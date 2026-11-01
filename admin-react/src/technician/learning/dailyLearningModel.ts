import type { LearningAssignment, LearningCourse } from './learningModel';
export const latestAttempt=(item:LearningAssignment)=>item.attempts.slice(-1)[0];
export function isComplete(item:LearningAssignment){const latest=latestAttempt(item);return !!latest && latest.total>0 && latest.correct===latest.total;}
export function priority(item:LearningAssignment){const latest=latestAttempt(item);return latest&&!isComplete(item)?0:item.sectionsRead.length&&!isComplete(item)?1:!isComplete(item)?2:3;}
export function orderedLessons(items:LearningAssignment[],courses:LearningCourse[]){return items.filter(item=>courses.some(c=>c.id===item.courseId&&c.version===item.courseVersion)).slice().sort((a,b)=>priority(a)-priority(b)||a.assignedAt.localeCompare(b.assignedAt)||courses.findIndex(c=>c.id===a.courseId)-courses.findIndex(c=>c.id===b.courseId)||a.id.localeCompare(b.id));}
export function progressLabel(item:LearningAssignment){const last=latestAttempt(item);return last ? isComplete(item)?'练习全对':`${last.total-last.correct} 道错题待复习` : item.sectionsRead.length?'继续学习':'还没开始';}
export function needsCoaching(item:LearningAssignment){const attempt=latestAttempt(item);return !!attempt&&!isComplete(item);}
