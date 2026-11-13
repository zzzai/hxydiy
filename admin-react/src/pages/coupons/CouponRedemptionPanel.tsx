import { useEffect, useState } from 'react';
import { Alert, App, Button, Select, Space, Table, Tag } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { exportCouponRecords, getCouponRedemptionEvents, getCoupons } from '../../api';
import { requestErrorMessage } from '../../requestError';
import { formatDateTime } from '../../utils/couponFormat';

type Redemption = {
  id: number; at: string | null; coupon_id: number; template_id: number; template_name: string;
  customer: string | null; phone_masked: string | null; actor_name: string; result: string;
};

export default function CouponRedemptionPanel({ storeId }: { storeId?: number }) {
  const [rows, setRows] = useState<Redemption[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [days, setDays] = useState(30);
  const [templateId, setTemplateId] = useState<number | undefined>();
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [exporting, setExporting] = useState(false);
  const { message } = App.useApp();

  useEffect(() => { void getCoupons(storeId).then(r => setTemplates((r.data?.items || []).map((t: any) => ({ value: t.id, label: t.name })))).catch(() => {}); }, [storeId]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void getCouponRedemptionEvents({ store_id: storeId, template_id: templateId, days, page, page_size: pageSize })
      .then((response) => { if (!active) return; setRows(response.data?.items || []); setTotal(response.data?.total || 0); })
      .catch((failure) => { if (active) { setRows([]); setTotal(0); setError(requestErrorMessage(failure)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, templateId, days, page, pageSize, attempt]);

  const exportAll = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const response = await exportCouponRecords({ dataset: 'redemptions', store_id: storeId, template_id: templateId, days });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = '核销记录.csv'; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch { message.error('导出失败，请重试'); }
    finally { setExporting(false); }
  };

  return <div>
    <div className="coupon-panel-head">
      <div><h2>核销记录</h2><p>按真实核销时间统计成功事件；较早领取、近期核销的券也在这里出现。</p></div>
      <Space wrap>
        <Select allowClear placeholder="全部券规则" style={{ width: 200 }} value={templateId} onChange={(value) => { setTemplateId(value); setPage(1); }} options={templates} />
        <Select style={{ width: 120 }} value={days} onChange={(value) => { setDays(value); setPage(1); }} options={[{ value: 7, label: '近 7 天' }, { value: 30, label: '近 30 天' }, { value: 90, label: '近 90 天' }]} />
        <Button icon={<ReloadOutlined />} onClick={() => setAttempt(v => v + 1)}>刷新</Button>
        <Button icon={<DownloadOutlined />} loading={exporting} onClick={() => void exportAll()}>导出当前筛选</Button>
      </Space>
    </div>
    {error ? <Alert type="error" showIcon message="核销记录加载失败" description={error} action={<Button size="small" onClick={() => setAttempt(v => v + 1)}>重试</Button>} style={{ marginBottom: 12 }} /> : null}
    <Table rowKey="id" size="small" loading={loading} dataSource={rows} scroll={{ x: 850 }}
      locale={{ emptyText: `近 ${days} 天没有核销记录` }}
      pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [20, 50, 100], onChange: (next, size) => { setPage(next); setPageSize(size); } }}
      columns={[
        { title: '核销时间', dataIndex: 'at', width: 180, render: (value: string | null) => formatDateTime(value) },
        { title: '券规则', dataIndex: 'template_name', render: (value: string) => <b>{value}</b> },
        { title: '券 ID', dataIndex: 'coupon_id', width: 80 },
        { title: '顾客', width: 160, render: (_: unknown, row: Redemption) => <span>{row.customer || '—'}<br /><small>{row.phone_masked || ''}</small></span> },
        { title: '操作人', dataIndex: 'actor_name', width: 130 },
        { title: '结果', width: 100, render: () => <Tag color="green">核销成功</Tag> },
      ]} />
    <Alert style={{ marginTop: 12 }} type="info" showIcon message="这不是营业收入"
      description="扫码核销只改变券状态，不创建支付订单、不扣钱包、不充值、不退款；没有订单关联时，不能把核销金额当收入或营销成本。" />
  </div>;
}
