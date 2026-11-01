export type LearningActor = { id: number; storeId: number; role: 'manager' | 'technician'; name: string };
export type LearningSection = { id: string; title: string; paragraphs: string[] };
export type LearningQuestion = { id: string; prompt: string; choices: string[]; answer?: number; explanation?: string };
export type LearningCourse = { id: string; version: string; title: string; category: string; minutes: string; intro: string; sections: LearningSection[]; questions: LearningQuestion[]; sources: Array<{ title: string; url: string }> };
export type LearningAttempt = { id: string; answers: Record<string, number>; correct: number; total: number; review?: Array<{questionId: string; answer: number; explanation: string}>; createdAt: string };
export type LearningFollowUp = { id: string; managerId: number; managerName: string; note: string; createdAt: string };
export type LearningAssignment = { id: string; storeId: number; staffId: number; staffName: string; courseId: string; courseVersion: string; assignedAt: string; dueAt: string | null; revision: number; sectionsRead: string[]; attempts: LearningAttempt[]; followUps: LearningFollowUp[] };
export type LearningState = { schema: 1; assignments: LearningAssignment[]; receipts: Record<string, string> };
export type LearningCommand = { kind: 'mark_section' | 'submit' | 'follow_up'; assignmentId: string; requestId: string; expectedRevision: number; sectionId?: string; answers?: Record<string, number>; note?: string };
export type LearningGateway = { list: (actor: LearningActor) => Promise<LearningAssignment[]>; execute: (actor: LearningActor, command: LearningCommand) => Promise<LearningAssignment[]>; currentActor: () => LearningActor | null };

export function learningIdentity(actor: LearningActor): string { return `${actor.storeId}:${actor.id}:${actor.role}`; }
export function visibleLearning(state: LearningState, actor: LearningActor): LearningAssignment[] {
  if (!['manager', 'technician'].includes(actor.role)) throw new Error('当前身份不能查看学习记录');
  return structuredClone(state.assignments.filter(item => item.storeId === actor.storeId && (actor.role === 'manager' || item.staffId === actor.id)));
}
export function learningStatus(item: LearningAssignment, course: LearningCourse): string {
  const latest = item.attempts[item.attempts.length - 1];
  if (latest) return latest.correct === latest.total ? '练习全对' : '有错题待复习';
  if (course.sections.every(section => item.sectionsRead.includes(section.id))) return '待做练习';
  return item.sectionsRead.length ? '学习中' : '未开始';
}
export function learningPeople(items: LearningAssignment[], courses: LearningCourse[]): number {
  return new Set(items.filter(item => {
    const course = courses.find(value => value.id === item.courseId && value.version === item.courseVersion);
    return !course || learningStatus(item, course) !== '练习全对';
  }).map(item => item.staffId)).size;
}
export function applyLearningCommand(state: LearningState, actor: LearningActor, command: LearningCommand, courses: LearningCourse[], now: string): LearningState {
  if (!['mark_section', 'submit', 'follow_up'].includes(command.kind)) throw new Error('不支持此学习操作');
  const original = state.assignments.find(item => item.id === command.assignmentId);
  if (!original || original.storeId !== actor.storeId || (actor.role !== 'manager' && original.staffId !== actor.id)) throw new Error('无权访问这项学习任务');
  if ((command.kind === 'follow_up' && actor.role !== 'manager') || (command.kind !== 'follow_up' && (actor.role !== 'technician' || original.staffId !== actor.id))) throw new Error('当前身份不能执行此操作');
  const course = courses.find(item => item.id === original.courseId && item.version === original.courseVersion);
  if (!course) throw new Error('课程版本已变化，请重新打开任务');
  if (!command.requestId || command.requestId.length > 100) throw new Error('提交编号无效，请重新打开任务');
  const receipt = `${learningIdentity(actor)}:${command.requestId}`;
  const fingerprint = JSON.stringify(command);
  if (state.receipts[receipt]) {
    if (state.receipts[receipt] !== fingerprint) throw new Error('提交内容已变化，请重新提交');
    return state;
  }
  if (original.revision !== command.expectedRevision) throw new Error('记录已更新，请刷新后再试；输入仍为您保留');
  const next = structuredClone(state);
  const item = next.assignments.find(value => value.id === original.id)!;
  if (command.kind === 'mark_section') {
    const index = course.sections.findIndex(section => section.id === command.sectionId);
    if (index < 0 || course.sections.slice(0, index).some(section => !item.sectionsRead.includes(section.id))) throw new Error('请先学习前面的内容');
    if (!item.sectionsRead.includes(command.sectionId!)) item.sectionsRead.push(command.sectionId!);
  } else if (command.kind === 'submit') {
    if (!course.sections.every(section => item.sectionsRead.includes(section.id))) throw new Error('请先读完本课内容');
    const answers = command.answers;
    if (!answers || Object.keys(answers).length !== course.questions.length || course.questions.some(q => !Number.isInteger(answers[q.id]) || answers[q.id] < 0 || answers[q.id] >= q.choices.length)) throw new Error('还有题目未作答，请补全后提交');
    const correct = course.questions.filter(q => q.answer === answers[q.id]).length;
    item.attempts.push({ id: command.requestId, answers: { ...answers }, correct, total: course.questions.length, createdAt: now });
  } else {
    const note = command.note?.trim();
    if (!note || note.length > 500) throw new Error('请填写 1 至 500 字的具体补学建议');
    item.followUps.push({ id: command.requestId, managerId: actor.id, managerName: actor.name, note, createdAt: now });
  }
  item.revision += 1;
  next.receipts[receipt] = fingerprint;
  return next;
}
