import { useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Select, Space, Table, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getLearningGovernance, getStaff } from '../api';
import { requestErrorMessage } from '../requestError';
import StoreScopeSelect from '../components/StoreScopeSelect';
import './coupons/coupon-admin.css';
import './learning-governance.css';

type Course = {
  id: string; code: string; version: string; status: string; title: string;
  category: string; minutes: number; section_titles: string[]; section_count: number;
  question_count: number; content_integrity: boolean; approval_reference_present: boolean;
  assigned: number; completed: number;
};
type LearningOverview = {
  store_id: number; days: number;
  config: { learning_enabled: boolean; ai_ready: boolean; ai_model: string | null };
  courses: Course[];
  assignments: { total: number; completed: number; employees: number };
  ai: { calls: number; success: number; error: number; total_tokens: number; items: any[] };
};

const STATUS: Record<string, { label: string; color: string }> = {
  published: { label: '已发布', color: 'green' },
  pilot: { label: '试运行', color: 'gold' },
  retired: { label: '已退役', color: 'default' },
};

export default function LearningGovernancePage() {
  const staff = getStaff();
  const [storeId, setStoreId] = useState<number | undefined>(staff?.store_id ?? undefined);
  const [data, setData] = useState<LearningOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(30);
  const [detail, setDetail] = useState<Course | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void getLearningGovernance(storeId, days)
      .then((response) => { if (active) setData(response.data); })
      .catch((failure) => { if (active) { setData(null); setError(requestErrorMessage(failure)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, days, attempt]);

  if (loading && !data) return <Card>正在读取学习治理数据…</Card>;
  if (error || !data) return <Card><Alert type="error" showIcon message="学习治理数据加载失败" description={error || '没有返回数据'} /><Button style={{ marginTop: 12 }} icon={<ReloadOutlined />} onClick={() => setAttempt(v => v + 1)}>重试</Button></Card>;
  const published = data.courses.filter(c => c.status === 'published').length;
  const integrityIssues = data.courses.filter(c => !c.content_integrity).length;

  return <div className="learning-admin-page">
    <div className="coupon-admin-header">
      <div><p className="coupon-kicker">学习 · 治理</p><h1>学习治理</h1><p>课程版本、员工进度和 AI 使用情况只读汇总；不会代答、评分或发证。</p></div>
      <Space wrap><StoreScopeSelect value={storeId} onChange={setStoreId} /><Tag color={data.config.learning_enabled ? 'green' : 'default'}>{data.config.learning_enabled ? '学习已启用' : '学习未启用'}</Tag></Space>
    </div>
    <Alert type={data.config.ai_ready ? 'success' : 'warning'} showIcon style={{ marginBottom: 14 }}
      message={data.config.ai_ready ? 'AI 教练配置就绪' : 'AI 教练未就绪'}
      description={data.config.ai_ready ? `模型：${data.config.ai_model}。只展示已记录的调用次数、失败数和 token 用量，不展示顾客或健康数据。` : '未配置模型或开关关闭；本页仅展示已有审计记录，不调用模型。'} />
    <div className="coupon-stat-grid learning-stat-grid">
      <Card size="small" className="coupon-stat-card"><span>课程版本</span><strong>{data.courses.length}</strong><small>{published} 个已发布</small></Card>
      <Card size="small" className="coupon-stat-card"><span>学习任务</span><strong>{data.assignments.total}</strong><small>{data.assignments.employees} 名员工</small></Card>
      <Card size="small" className="coupon-stat-card"><span>已提交</span><strong>{data.assignments.completed}</strong><small>不是能力合格结论</small></Card>
      <Card size="small" className="coupon-stat-card"><span>AI 调用</span><strong>{data.ai.calls}</strong><small>{data.ai.error} 次失败 · {data.ai.total_tokens} tokens</small></Card>
      <Card size="small" className="coupon-stat-card"><span>内容异常</span><strong>{integrityIssues}</strong><small>哈希不一致时不得继续学习</small></Card>
    </div>
    {integrityIssues > 0 ? <Alert type="error" showIcon style={{ marginBottom: 12 }} message="有课程内容哈希不一致" description="旧成绩和员工进度保留；修复前不得用于新学习或自动判定。" /> : null}
    <Card title="课程版本" size="small" extra={<Space><Select value={days} onChange={setDays} style={{ width: 110 }} options={[{ value: 7, label: '近 7 天' }, { value: 30, label: '近 30 天' }, { value: 90, label: '近 90 天' }]} /><Button size="small" icon={<ReloadOutlined />} onClick={() => setAttempt(v => v + 1)}>刷新</Button></Space>} style={{ marginBottom: 14 }}>
      <Table rowKey="id" size="small" dataSource={data.courses} pagination={false} scroll={{ x: 800 }}
        columns={[
          { title: '课程', dataIndex: 'title', width: 220, render: (value: string, row: Course) => <div><b>{value}</b><div className="coupon-code">{row.code} · {row.version}</div></div> },
          { title: '状态', dataIndex: 'status', width: 90, render: (value: string) => <Tag color={STATUS[value]?.color}>{STATUS[value]?.label || value}</Tag> },
          { title: '内容', width: 130, render: (_: unknown, row: Course) => `${row.section_count} 节 · ${row.question_count} 题` },
          { title: '适用范围', width: 100, render: () => '本店可见' },
          { title: '进度', width: 120, render: (_: unknown, row: Course) => `${row.completed} / ${row.assigned}` },
          { title: '内容校验', width: 110, render: (_: unknown, row: Course) => row.content_integrity ? <Tag color="green">哈希一致</Tag> : <Tag color="red">待核验</Tag> },
          { title: '审批依据', width: 110, render: (_: unknown, row: Course) => row.approval_reference_present ? '已记录' : '未记录' },
          { title: '操作', width: 80, render: (_: unknown, row: Course) => <Button type="link" size="small" onClick={() => setDetail(row)}>预览</Button> },
        ]} />
    </Card>
    <Card title={`AI 使用记录（近 ${days} 天）`} size="small">
      <Table rowKey="id" size="small" dataSource={data.ai.items} pagination={false} locale={{ emptyText: '还没有 AI 调用记录' }}
        columns={[
          { title: '时间', dataIndex: 'at', width: 180, render: (value: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—' },
          { title: '员工', dataIndex: 'actor', width: 120 },
          { title: '动作', dataIndex: 'action', width: 180, render: (value: string) => value === 'learning_ai_coach' ? 'AI 教练' : 'AI 周计划' },
          { title: '结果', dataIndex: 'status', width: 100, render: (value: string) => <Tag color={value === 'success' ? 'green' : 'red'}>{value === 'success' ? '成功' : value === 'error' ? '失败' : '无依据/降级'}</Tag> },
          { title: '耗时', dataIndex: 'latency_ms', width: 100, render: (value: number) => value ? `${value}ms` : '—' },
          { title: 'tokens', dataIndex: 'total_tokens', width: 90, render: (value: number) => value || '—' },
        ]} />
      <p className="coupon-footnote">tokens 是已有审计记录中的用量，不推导费用金额；没有价格依据不展示成本。</p>
    </Card>
    <Drawer open={Boolean(detail)} onClose={() => setDetail(null)} width={520} title={detail ? `${detail.title} · ${detail.version}` : '课程版本'}>
      {detail ? <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="课程编码">{detail.code}</Descriptions.Item>
        <Descriptions.Item label="版本">{detail.version}</Descriptions.Item>
        <Descriptions.Item label="状态">{STATUS[detail.status]?.label || detail.status}</Descriptions.Item>
        <Descriptions.Item label="适用范围">本店员工；版本不覆盖旧版本成绩和进度</Descriptions.Item>
        <Descriptions.Item label="内容校验">{detail.content_integrity ? 'SHA256 一致' : 'SHA256 不一致，停止新学习'}</Descriptions.Item>
        <Descriptions.Item label="章节">{detail.section_titles.join(' · ') || '未记录'}</Descriptions.Item>
        <Descriptions.Item label="题目">共 {detail.question_count} 题；预览不展示答案和解析</Descriptions.Item>
        <Descriptions.Item label="已安排 / 已提交">{detail.assigned} / {detail.completed}</Descriptions.Item>
      </Descriptions> : null}
    </Drawer>
  </div>;
}
