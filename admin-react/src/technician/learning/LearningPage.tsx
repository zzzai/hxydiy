import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeftOutlined, ArrowRightOutlined, ReadOutlined } from '@ant-design/icons';
import type { LearningActor, LearningAssignment, LearningCommand, LearningCourse, LearningGateway } from './learningModel';
import { learningIdentity, learningPeople, learningStatus } from './learningModel';
import './learning.css';

type Props = { actor: LearningActor; courses: LearningCourse[]; gateway: LearningGateway };
const latestAttempt = (item: LearningAssignment) => item.attempts[item.attempts.length - 1];
const dateLabel = (value: string) => new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
const draftKey = (actor: LearningActor, item: LearningAssignment) => `hxy_learning_preview_draft:v7:${learningIdentity(actor)}:${item.id}:${item.courseVersion}`;
function readDraft(actor: LearningActor, item: LearningAssignment, course: LearningCourse): Record<string, number> {
  try {
    const data = JSON.parse(sessionStorage.getItem(draftKey(actor, item)) || '{}');
    return Object.fromEntries(course.questions.filter(q => Number.isInteger(data[q.id]) && data[q.id] >= 0 && data[q.id] < q.choices.length).map(q => [q.id, data[q.id]]));
  } catch { return {}; }
}

export function LearningEntry({ actor, courses, gateway }: Props) {
  const navigate = useNavigate();
  const [items, setItems] = useState<LearningAssignment[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    void gateway.list(actor).then(data => { if (active) setItems(data); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [actor, gateway]);
  const manager = actor.role === 'manager';
  const count = items ? (manager ? learningPeople(items, courses) : items.filter(item => learningStatus(item, courses.find(course => course.id === item.courseId && course.version === item.courseVersion)!) !== '练习全对').length) : null;
  return <button className="learning-entry" onClick={() => navigate('/learning')}><ReadOutlined aria-hidden /><span><strong>{manager ? '团队学习' : '本次学习'}</strong><small>{failed ? '暂未取得进度，点开重试' : count === null ? '正在读取学习进度' : count ? manager ? `${count} 人待学习或需复习` : `${count} 课待完成练习` : items?.length ? '本次练习已全部答对' : '暂未安排学习任务'}</small></span><ArrowRightOutlined aria-hidden /></button>;
}

export default function LearningPage({ actor, courses, gateway }: Props) {
  const navigate = useNavigate();
  const [items, setItems] = useState<LearningAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [phase, setPhase] = useState<'read' | 'quiz' | 'result'>('read');
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [note, setNote] = useState('');
  const [savedNote, setSavedNote] = useState(false);
  const [filter, setFilter] = useState<'attention' | 'all'>('attention');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const pending = useRef<{ payload: string; command: LearningCommand }>();
  const manager = actor.role === 'manager';
  const item = items.find(value => value.id === selected);
  const course = item && courses.find(value => value.id === item.courseId && value.version === item.courseVersion);
  const current = () => alive.current && gateway.currentActor() !== null && learningIdentity(gateway.currentActor()!) === learningIdentity(actor);
  const load = async () => {
    setLoading(true); setError('');
    try { const values = await gateway.list(actor); if (current()) setItems(values); }
    catch (failure) { if (current()) setError(failure instanceof Error ? failure.message : '学习进度未能读取，请重试'); }
    finally { if (current()) setLoading(false); }
  };
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, [actor, gateway]);
  const open = (value: LearningAssignment) => {
    const target = courses.find(c => c.id === value.courseId && c.version === value.courseVersion);
    if (!target) { setError('课程版本暂不可用，请联系课程负责人'); return; }
    setSelected(value.id); setError(''); setNote(''); setSavedNote(false); pending.current = undefined;
    const firstUnread = target.sections.findIndex(section => !value.sectionsRead.includes(section.id));
    setStep(firstUnread < 0 ? 0 : firstUnread);
    setPhase(value.attempts.length ? 'result' : firstUnread < 0 ? 'quiz' : 'read');
    setAnswers(readDraft(actor, value, target));
    window.scrollTo(0, 0);
  };
  const run = async (body: Omit<LearningCommand, 'requestId' | 'expectedRevision' | 'assignmentId'>) => {
    if (!item || busyRef.current || !current()) return false;
    const payload = JSON.stringify({ item: item.id, ...body });
    if (pending.current?.payload !== payload) pending.current = { payload, command: { ...body, assignmentId: item.id, requestId: crypto.randomUUID(), expectedRevision: item.revision } };
    busyRef.current = true; setBusy(true); setError('');
    try {
      const result = await gateway.execute(actor, pending.current.command);
      if (!current()) return false;
      setItems(result); pending.current = undefined; return true;
    } catch (failure) {
      if (current()) setError(failure instanceof Error ? failure.message : '保存未成功，请重试；已保留输入');
      return false;
    } finally { busyRef.current = false; if (current()) setBusy(false); }
  };
  const nextSection = async () => {
    if (!course || !await run({ kind: 'mark_section', sectionId: course.sections[step].id })) return;
    if (step === course.sections.length - 1) setPhase('quiz'); else setStep(value => value + 1);
    window.scrollTo(0, 0);
  };
  const answer = (id: string, value: number) => {
    if (!item) return;
    const next = { ...answers, [id]: value }; setAnswers(next); pending.current = undefined;
    try { sessionStorage.setItem(draftKey(actor, item), JSON.stringify(next)); }
    catch { setError('本机暂不能保存选项，请保持此页并完成提交'); }
  };
  const submit = async () => {
    if (!item || !course) return;
    if (course.questions.some(q => answers[q.id] === undefined)) { setError('还有题目未作答，请补全后提交'); return; }
    if (!await run({ kind: 'submit', answers })) return;
    sessionStorage.removeItem(draftKey(actor, item)); setPhase('result'); window.scrollTo(0, 0);
  };
  const back = () => {
    if (busyRef.current) return;
    if (selected) { setSelected(null); setError(''); pending.current = undefined; void load(); }
    else navigate(manager ? '/store' : '/today');
  };
  const retryPractice = () => { if (!item) return; setAnswers({}); sessionStorage.removeItem(draftKey(actor, item)); pending.current = undefined; setPhase('quiz'); window.scrollTo(0, 0); };
  const attempts = item?.attempts || [];
  const latest = item && latestAttempt(item);
  const followUps = (value: LearningAssignment) => value.followUps.length > 0 && <section className="learning-follow-ups"><h3>{manager ? '跟进记录' : '店长的补学建议'}</h3>{[...value.followUps].reverse().map(record => <article key={record.id}><p>{record.note}</p><small>{record.managerName} · {dateLabel(record.createdAt)}</small></article>)}</section>;
  const reviewedQuestions = latest && course ? course.questions.map(q => {
    const reviewed = latest.review?.find(value => value.questionId === q.id);
    return { ...q, answer: reviewed?.answer ?? q.answer, explanation: reviewed?.explanation ?? q.explanation };
  }).filter(q => q.answer !== undefined) : [];
  const results = () => latest && course && <>
    <div className="learning-result"><span>最近一次练习</span><strong>答对 {latest.correct} / {latest.total} 题</strong><p>{latest.correct === latest.total ? '本课练习已全部答对' : '先复习下面的错题，再做一次练习'}</p><small>{dateLabel(latest.createdAt)} · {course.version === 'pilot-v1' ? '试讲第 1 版' : course.version}</small></div>
    {reviewedQuestions.filter(q => latest.answers[q.id] !== q.answer).map(q => <article className="learning-wrong" key={q.id}><h3>{q.prompt}</h3><p>本次选择：{q.choices[latest.answers[q.id]]}</p><p className="learning-correct">参考答案：{q.choices[q.answer!]}</p><small>{q.explanation}</small></article>)}
    <p className="learning-note">这是样课练习结果，不作为实操合格证明。</p>
    <details className="learning-history"><summary>历次练习（{attempts.length} 次）</summary>{[...attempts].reverse().map((attempt, index) => <p key={attempt.id}>第 {attempts.length - index} 次：{attempt.correct}/{attempt.total} 题 · {dateLabel(attempt.createdAt)}</p>)}</details>
  </>;
  return <section className="learning-page">
    <button className="learning-back" onClick={back} disabled={busy}><ArrowLeftOutlined aria-hidden />{selected ? manager ? '返回团队学习' : '返回我的学习' : '返回工作台'}</button>
    {error && <div className="learning-error" role="alert"><p>{error}</p><button onClick={() => { pending.current = undefined; void load(); }} disabled={busy}>刷新进度</button></div>}
    {loading && !item ? <p role="status">正在读取学习进度…</p> : !item ? <>
      <h1>{manager ? '团队学习' : '我的学习'}</h1>
      <p className="learning-subtitle">{manager ? '先看谁需要帮助，再看具体错在哪里。' : '每次学一点，把服务做好一点。'}</p>
      {manager && <div className="learning-filter" role="group" aria-label="学习人员筛选"><button aria-pressed={filter === 'attention'} onClick={() => setFilter('attention')}>需跟进 {learningPeople(items, courses)}</button><button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>全部人员</button></div>}
      {manager ? [...new Set(items.map(value => value.staffId))].filter(id => filter === 'all' || items.some(value => value.staffId === id && learningStatus(value, courses.find(c => c.id === value.courseId && c.version === value.courseVersion)!) !== '练习全对')).map(id => <article className="learning-person" key={id}><h2>{items.find(value => value.staffId === id)?.staffName}</h2>{items.filter(value => value.staffId === id).map(value => <button className="learning-task-row" key={value.id} onClick={() => open(value)}><span><strong>{courses.find(c => c.id === value.courseId && c.version === value.courseVersion)?.category}</strong><small>{learningStatus(value, courses.find(c => c.id === value.courseId && c.version === value.courseVersion)!)}</small></span><ArrowRightOutlined aria-hidden /></button>)}</article>) : items.map(value => {
        const c = courses.find(entry => entry.id === value.courseId && entry.version === value.courseVersion);
        return c && <button className="learning-course-row" key={value.id} onClick={() => open(value)}><span className="learning-category">{c.category}</span><strong>{c.title}</strong><small>{c.minutes} · {learningStatus(value, c)}</small>{value.followUps.length > 0 && <span className="learning-follow-up-flag">有店长的补学建议</span>}<ArrowRightOutlined aria-hidden /></button>;
      })}
      {items.length === 0 && <p className="learning-empty">暂未安排学习任务</p>}
      {manager && items.length > 0 && filter === 'attention' && learningPeople(items, courses) === 0 && <p className="learning-empty">本次已安排的练习均已答对，可在全部人员中查看记录。</p>}
    </> : course && manager ? <>
      <h1>{item.staffName}</h1><p className="learning-subtitle">{course.category} · {course.title}</p>
      <div className="learning-progress-line"><span>内容学习</span><strong>{item.sectionsRead.length}/{course.sections.length} 节已读</strong></div>
      <div className="learning-progress-line"><span>练习情况</span><strong>{learningStatus(item, course)}</strong></div>
      {latest ? results() : <p className="learning-note">尚无练习记录。先了解是否安排了学习时间。</p>}
      <form className="learning-coach" onSubmit={async event => { event.preventDefault(); if (await run({ kind: 'follow_up', note })) { setNote(''); setSavedNote(true); } }}><label htmlFor="learning-followup">给出具体补学建议</label><textarea id="learning-followup" value={note} maxLength={500} disabled={busy} onChange={event => { setNote(event.target.value); pending.current = undefined; setSavedNote(false); }} placeholder="例如：一起演练一次顾客说不舒服时怎么回应，再复习第 3 题。"/><button className="learning-primary" disabled={busy || !note.trim()}>{busy ? '正在保存…' : '保存跟进记录'}</button>{savedNote && <p role="status" className="learning-note">已保存，技师打开本课即可查看。</p>}</form>{followUps(item)}
    </> : course && <>
      <span className="learning-category">{course.category} · {course.minutes}</span><h1>{course.title}</h1>{followUps(item)}
      {phase === 'read' ? <><div className="learning-step">学习内容 {step + 1} / {course.sections.length}</div><article className="learning-reader"><h2>{course.sections[step].title}</h2>{course.sections[step].paragraphs.map((text, i) => <p key={i}>{text}</p>)}</article><div className="learning-actions">{step > 0 && <button className="learning-secondary" disabled={busy} onClick={() => setStep(value => value - 1)}>上一节</button>}<button className="learning-primary" disabled={busy} onClick={() => void nextSection()}>{busy ? '正在保存…' : step === course.sections.length - 1 ? '开始练习' : '读完，继续下一节'}</button></div></> : phase === 'quiz' ? <form onSubmit={event => { event.preventDefault(); void submit(); }}><p className="learning-note">每题选一个答案。返回后可继续本次未提交选项。</p>{course.questions.map((q, index) => <fieldset className="learning-question" key={q.id} disabled={busy}><legend>{index + 1}. {q.prompt}</legend>{q.choices.map((choice, value) => <label key={value}><input type="radio" name={q.id} value={value} checked={answers[q.id] === value} onChange={() => answer(q.id, value)}/><span>{choice}</span></label>)}</fieldset>)}<button className="learning-primary" disabled={busy}>{busy ? '正在提交…' : '提交练习，查看解析'}</button></form> : <>{results()}<div className="learning-actions"><button className="learning-secondary" onClick={() => { setStep(0); setPhase('read'); }}>再读一遍</button><button className="learning-primary" onClick={retryPractice}>重新练习</button></div></>}
      {course.sources.length > 0 && <details className="learning-sources"><summary>学习依据</summary><ul>{course.sources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a></li>)}</ul><p>本课为经络名称与编码基础。标准信息及公开摘录已核对，定位正文未逐条审阅；没有人体定位图或操作参数。</p></details>}
    </>}
  </section>;
}
