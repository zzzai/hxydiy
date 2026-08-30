import { useState, useEffect } from 'react';
import { Card, Spin, Empty, Button, Progress, DatePicker, Row, Col, Statistic, Table, Tag, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { getAnalytics, getOperationsSummary } from '../api';

const funnelKeys = ['diy_entry_view', 'project_view', 'project_config_save', 'selection_submit_success', 'feedback_submit_success'] as const;
const funnelText: Record<string, string> = { diy_entry_view: '进入 DIY', project_view: '查看项目', project_config_save: '保存配置', selection_submit_success: '提交前台', feedback_submit_success: '完成评价' };
const statusText: Record<string, string> = { available: '可用', held: '已占用', waiting_service: '待服务', in_service: '服务中', post_service_present: '服务后在场', cleaning: '清洁中' };
const funnelRateKeys: Record<string, string> = {
  diy_entry_view: 'diy_entry_view_to_project_view_percent',
  project_view: 'project_view_to_selection_submit_success_percent',
  selection_submit_success: 'selection_submit_success_to_feedback_submit_success_percent',
};

function formatYuan(cents = 0) { return `¥${(cents / 100).toFixed(2)}`; }

export default function AnalyticsPage() {
  const navigate = useNavigate();
  const [behavior, setBehavior] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(6, 'day'), dayjs()]);
  const [loading, setLoading] = useState(true);

  const load = async (selectedRange = range) => {
    setLoading(true);
    try {
      const start = selectedRange[0].format('YYYY-MM-DD');
      const end = selectedRange[1].format('YYYY-MM-DD');
      const [behaviorResponse, summaryResponse] = await Promise.all([
        getAnalytics(Math.max(1, selectedRange[1].diff(selectedRange[0], 'day') + 1)),
        getOperationsSummary(start, end),
      ]);
      setBehavior(behaviorResponse.data);
      setSummary(summaryResponse.data);
    } catch {} finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading && !summary) return <Spin style={{ display: 'block', margin: '40px auto' }} />;
  if (!summary || !behavior) return <Empty description="暂无数据" />;

  const maxFunnel = Math.max(...funnelKeys.map(k => behavior.funnel?.[k] || 0), 1);
  const transaction = summary.transactions || {};
  const customers = summary.customers || {};
  const positions = summary.service_positions || {};
  const operations = positions.operations || {};
  const feedback = summary.feedback || {};
  const statusRows = Object.entries(positions.status_counts || {}).map(([status, count]) => ({ key: status, status, count }));

  return (
    <div>
      <div className="page-heading">
        <div><h2>经营分析</h2><div className="page-kicker">按门店权限展示经营事实，金额均为人民币</div></div>
        <Space wrap>
          <DatePicker.RangePicker
            value={range}
            allowClear={false}
            format="YYYY-MM-DD"
            onChange={(value) => {
              if (value?.[0] && value?.[1]) {
                const next: [Dayjs, Dayjs] = [value[0], value[1]];
                setRange(next);
                load(next);
              }
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
        </Space>
      </div>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card><Statistic title="实收金额" value={formatYuan(transaction.paid_amount_cents)} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="订单数" value={transaction.orders_count || 0} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="优惠金额" value={formatYuan(transaction.discount_cents)} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="服务位" value={positions.total_count || 0} suffix={`活跃 ${positions.active_count || 0}`} /></Card></Col>
      </Row>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="顾客结构">
            <Row gutter={[8, 18]}>
              <Col span={12}><Statistic title="新客" value={customers.new_count || 0} /></Col>
              <Col span={12}><Statistic title="复购顾客" value={customers.repeat_count || 0} /></Col>
              <Col span={12}><Statistic title="会员顾客" value={customers.member_count || 0} /></Col>
              <Col span={12}><Statistic title="匿名转登录" value={customers.anonymous_to_logged_in_count || 0} /></Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="评价概览">
            <Row gutter={[8, 18]}>
              <Col span={8}><Statistic title="评价数" value={feedback.count || 0} /></Col>
              <Col span={8}><Statistic title="平均分" value={feedback.average_rating ?? '-'} precision={2} /></Col>
              <Col span={8}><Button type="link" onClick={() => navigate('/feedback')} style={{ padding: 0, height: 'auto', textAlign: 'left' }}><Statistic title="低分待跟进" value={feedback.low_rating_count || 0} valueStyle={{ color: feedback.low_rating_count ? '#c0392b' : undefined }} /></Button></Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} lg={12}>
          <Card title="服务位运营" style={{ height: '100%' }}>
            <Row gutter={[8, 18]} style={{ marginBottom: 18 }}>
              <Col span={12}><Statistic title="完成服务" value={operations.completed_services_count || 0} /></Col>
              <Col span={12}><Statistic title="周转次数" value={operations.turnover_count || 0} /></Col>
              <Col span={12}><Statistic title="平均服务时长" value={operations.average_service_minutes || 0} suffix="分钟" /></Col>
              <Col span={12}><Statistic title="平均离位到释放" value={operations.average_departure_to_release_minutes || 0} suffix="分钟" /></Col>
              <Col span={12}><Statistic title="服务位利用率" value={operations.utilization_percent || 0} suffix="%" /></Col>
              <Col span={12}><Statistic title="异常结束" value={operations.exception_release_count || 0} /></Col>
            </Row>
            <div style={{ color: '#7f8c8d', fontSize: 12, marginBottom: 12 }}>清洁耗时：当前数据未记录清洁开始时间，暂不计算</div>
            <Table
              size="small"
              pagination={false}
              dataSource={statusRows}
              columns={[
                { title: '状态', dataIndex: 'status', render: (status: string) => <Tag>{statusText[status] || status}</Tag> },
                { title: '数量', dataIndex: 'count' },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="扫码到评价去重漏斗" style={{ height: '100%' }}>
            {funnelKeys.map(k => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ width: 76, flex: '0 0 auto', fontSize: 13 }}>{funnelText[k]}</span>
                <Progress percent={Math.round((summary.funnel?.[k] || 0) / maxFunnel * 100)} size="small" style={{ flex: 1, margin: '0 12px' }} strokeColor={k === 'selection_submit_success' ? '#e67e22' : '#1f8f75'} showInfo={false} />
                <span style={{ width: 90, textAlign: 'right', fontWeight: 600 }}>
                  {summary.funnel?.[k] || 0}{funnelRateKeys[k] && <span style={{ display: 'block', color: '#7f8c8d', fontSize: 11 }}>{summary.funnel_rates?.[funnelRateKeys[k]] ?? 0}% 到下一阶段</span>}
                </span>
              </div>
            ))}
          </Card>
        </Col>
      </Row>

      <Card title="项目热度 Top5" style={{ marginTop: 16 }}>
        {(behavior.hot_projects || []).length ? behavior.hot_projects.map((project: any) => (
          <div key={project.project_id} style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ width: 100, fontSize: 13 }}>{project.name}</span>
            <Progress percent={Math.round(project.views / (behavior.hot_projects?.[0]?.views || 1) * 100)} size="small" style={{ flex: 1, margin: '0 12px' }} showInfo={false} />
            <span style={{ fontWeight: 600 }}>{project.views}</span>
          </div>
        )) : <Empty description="暂无项目浏览数据" />}
      </Card>
    </div>
  );
}
