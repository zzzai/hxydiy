import { useState } from 'react';
import { Button, Input, Modal, Select, Tag, message } from 'antd';
import { CheckCircleFilled, TeamOutlined } from '@ant-design/icons';
import { confirmManagerAssessment, getManagerTeam } from '../api';

type Team = Awaited<ReturnType<typeof getManagerTeam>>['data'];
type Tech = Team['technicians'][number];

const hqLabel: Record<string, string> = { pending: '待总部抽检', passed: '总部已通过', returned: '总部退回' };
const hqColor: Record<string, string> = { pending: 'gold', passed: 'green', returned: 'red' };

export default function ManagerTeamView({ team, onRefresh }: { team: Team | null; onRefresh: () => Promise<void> }) {
  const [selected, setSelected] = useState<Tech | null>(null);
  const [course, setCourse] = useState('');
  const [kind, setKind] = useState('practical');
  const [result, setResult] = useState('passed');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const open = (tech: Tech) => {
    setSelected(tech);
    setCourse(tech.learning?.title || tech.assessment?.course_name || '');
    setKind(tech.assessment?.kind || 'practical');
    setResult('passed');
    setNote('');
  };

  const confirm = async () => {
    if (!selected || !course.trim() || saving) return;
    setSaving(true);
    try {
      await confirmManagerAssessment(selected.staff_id, {
        course_name: course.trim(), kind, result, note: note.trim(),
        assignment_id: selected.learning?.assignment_id,
      });
      await onRefresh();
      setSelected(null);
      message.success('已提交店长确认，等待总部抽检');
    } catch (failure) {
      const detail = (failure as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '提交失败');
    } finally { setSaving(false); }
  };

  if (!team) return <div className="manager-p0-loading">团队学习加载中…</div>;
  return <div className="manager-p0-stack">
    <section className="manager-p0-team-summary">
      <div><strong>{team.summary.staff_count}</strong><small>在岗技师</small></div>
      <div><strong>{team.summary.on_track}</strong><small>本周达标</small></div>
      <div className={team.summary.overdue ? 'warn' : ''}><strong>{team.summary.overdue}</strong><small>待跟进</small></div>
    </section>
    <div className="manager-p0-section-title"><div><small>本周培训计划</small><h2>学习与考核</h2></div><TeamOutlined /></div>
    {team.technicians.map((tech: Tech) => <section className="manager-p0-card manager-p0-tech" key={tech.staff_id} onClick={() => open(tech)}>
      <div className="manager-p0-avatar">{tech.name.slice(0, 1)}</div>
      <div className="manager-p0-tech-main">
        <div className="manager-p0-tech-name"><strong>{tech.name}</strong>{tech.overdue && <Tag color="red">逾期</Tag>}</div>
        <small>{tech.learning?.title || '本周暂无学习任务'} · {tech.progress}%</small>
        <div className="manager-p0-tech-bar"><i style={{ width: `${tech.progress}%` }} /></div>
        <small>{tech.assessment ? `${tech.assessment.course_name} · ${tech.assessment.result === 'passed' ? '已通过' : '待复训'}` : '尚未提交考核'}</small>
      </div>
      <div className="manager-p0-tech-side">
        {tech.assessment ? <Tag color={hqColor[tech.assessment.hq_status]}>{hqLabel[tech.assessment.hq_status]}</Tag> : <Tag>待确认</Tag>}
        <span>{tech.progress}%</span>
      </div>
    </section>)}
    {!team.technicians.length && <div className="manager-p0-empty">本店暂无在岗技师</div>}
    <p className="manager-p0-fine">店长确认后进入总部抽检；总部退回的考核会显示“待复训”。</p>

    <Modal open={Boolean(selected)} title="店长确认考核" footer={null} onCancel={() => setSelected(null)}>
      <div className="manager-p0-modal-form">
        <label>考核项目<Input value={course} onChange={(event) => setCourse(event.target.value)} placeholder="如：足部精修实操" /></label>
        <label>类型<Select value={kind} onChange={setKind} options={[{ value: 'practical', label: '实操' }, { value: 'theory', label: '理论' }]} /></label>
        <label>结果<Select value={result} onChange={setResult} options={[{ value: 'passed', label: '通过' }, { value: 'failed', label: '待复训' }]} /></label>
        <label>备注<Input.TextArea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={500} placeholder="带教情况、需要复训的点" /></label>
        <Button type="primary" block loading={saving} disabled={!course.trim()} onClick={() => void confirm()}><CheckCircleFilled /> 确认并提交总部抽检</Button>
      </div>
    </Modal>
  </div>;
}
