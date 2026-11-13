import { useEffect, useState } from 'react';
import { Alert, App, Button, Descriptions, Drawer, Select, Space, Table, Tag } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { exportCouponRecords, getCouponLedger, getCoupons } from '../../api';
import { requestErrorMessage } from '../../requestError';
import { formatDateTime } from '../../utils/couponFormat';

type Ledger = {
  id: number; template_id: number; template_name: string;
  customer: string | null; phone_masked: string | null;
  status: 'unused' | 'locked' | 'used' | 'expired'; stored_status: string;
  source: 'poster' | 'direct' | 'unknown'; claimed_at: string | null;
  expire_at: string | null; used_order_id: number | null;
};

const SOURCE_LABEL: Record<string, string> = { poster: '海报领取', direct: '店长直接发', unknown: '历史未记录' };
const STATUS_LABEL: Record<string, string> = { unused: '待使用', locked: '锁定中', used: '已核销', expired: '已过期' };
const STATUS_COLOR: Record<string, string> = { unused: 'gold', locked: 'blue', used: 'green', expired: 'default' };

function dateText(value: string | null) { return formatDateTime(value); }

export default function CouponLedgerPanel({ storeId }: { storeId?: number }) {
  const [rows, setRows] = useState<Ledger[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<string | undefined>();
  const [templateId, setTemplateId] = useState<number | undefined>();
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<Ledger | null>(null);
  const [exporting, setExporting] = useState(false);
  const { message } = App.useApp();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => { void getCoupons(storeId).then(r => setTemplates((r.data?.items || []).map((t: any) => ({ value: t.id, label: t.name })))).catch(() => {}); }, [storeId]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void getCouponLedger({ store_id: storeId, template_id: templateId, status, page, page_size: pageSize })
      .then((response) => { if (!active) return; setRows(response.data?.items || []); setTotal(response.data?.total || 0); })
      .catch((failure) => { if (active) { setRows([]); setTotal(0); setError(requestErrorMessage(failure)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, templateId, status, page, pageSize, attempt]);

  const exportAll = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const response = await exportCouponRecords({ dataset: 'ledger', store_id: storeId, template_id: templateId, status });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = '券台账.csv'; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
    } catch { message.error('导出失败，请重试'); }
    finally { setExporting(false); }
  };

  return <div>
    <div className="coupon-panel-head">
      <div><h2>券台账</h2><p>这里是一张张顾客券的当前台账，不是核销事件流水；缺失来源显示“历史未记录”。</p></div>
      <Space wrap>
        <Select allowClear placeholder="全部券规则" style={{ width: 200 }} value={templateId} onChange={(value) => { setTemplateId(value); setPage(1); }} options={templates} />
        <Select allowClear placeholder="全部状态" style={{ width: 140 }} value={status} onChange={(value) => { setStatus(value); setPage(1); }} options={[{ value: 'unused', label: '待使用' }, { value: 'locked', label: '锁定中' }, { value: 'used', label: '已核销' }, { value: 'expired', label: '已过期' }]} />
        <Button icon={<ReloadOutlined />} onClick={() => setAttempt(v => v + 1)}>刷新</Button>
        <Button icon={<DownloadOutlined />} loading={exporting} onClick={() => void exportAll()}>导出当前筛选</Button>
      </Space>
    </div>
    {error ? <Alert type="error" showIcon message="券台账加载失败" description={error} action={<Button size="small" onClick={() => setAttempt(v => v + 1)}>重试</Button>} style={{ marginBottom: 12 }} /> : null}
    <Table rowKey="id" size="small" loading={loading} dataSource={rows} scroll={{ x: 950 }}
      pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [20, 50, 100], onChange: (next, size) => { setPage(next); setPageSize(size); } }}
      columns={[
        { title: '券 ID', dataIndex: 'id', width: 80 },
        { title: '券规则', dataIndex: 'template_name', render: (value: string) => <b>{value}</b> },
        { title: '顾客', width: 160, render: (_: unknown, row: Ledger) => <span>{row.customer || '—'}<br /><small>{row.phone_masked || ''}</small></span> },
        { title: '来源', width: 110, render: (_: unknown, row: Ledger) => SOURCE_LABEL[row.source] || SOURCE_LABEL.unknown },
        { title: '状态', width: 90, render: (_: unknown, row: Ledger) => <Tag color={STATUS_COLOR[row.status]}>{STATUS_LABEL[row.status]}</Tag> },
        { title: '领取时间', dataIndex: 'claimed_at', width: 170, render: dateText },
        { title: '到期时间', dataIndex: 'expire_at', width: 170, render: dateText },
        { title: '操作', width: 80, render: (_: unknown, row: Ledger) => <Button type="link" size="small" onClick={() => setDetail(row)}>详情</Button> },
      ]} />
    <Drawer open={Boolean(detail)} width={480} title={detail ? `券 #${detail.id}` : '券详情'} onClose={() => setDetail(null)}>
      {detail ? <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="券规则">{detail.template_name}</Descriptions.Item>
        <Descriptions.Item label="顾客">{detail.customer || '—'} {detail.phone_masked ? `· ${detail.phone_masked}` : ''}</Descriptions.Item>
        <Descriptions.Item label="当前状态">{STATUS_LABEL[detail.status]}</Descriptions.Item>
        <Descriptions.Item label="存储状态">{detail.stored_status}</Descriptions.Item>
        <Descriptions.Item label="来源">{SOURCE_LABEL[detail.source] || SOURCE_LABEL.unknown}</Descriptions.Item>
        <Descriptions.Item label="领取时间">{dateText(detail.claimed_at)}</Descriptions.Item>
        <Descriptions.Item label="到期时间">{dateText(detail.expire_at)}</Descriptions.Item>
        <Descriptions.Item label="使用订单">{detail.used_order_id || '未关联订单；扫码核销不创建支付订单'}</Descriptions.Item>
        <Descriptions.Item label="金额">{detail.used_order_id ? '见关联订单' : `本券无新增支付金额`}</Descriptions.Item>
      </Descriptions> : null}
    </Drawer>
  </div>;
}
