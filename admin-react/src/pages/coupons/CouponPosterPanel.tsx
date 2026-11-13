import { useEffect, useState } from 'react';
import { Alert, App, Button, Modal, Select, Space, Spin, Table, Tag } from 'antd';
import { DownloadOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import { getCouponPosterLink, getCouponPosters, getCoupons, getStaff } from '../../api';
import { requestErrorMessage } from '../../requestError';
import { formatDateTime } from '../../utils/couponFormat';
import { createCouponPoster } from '../../technician/couponPoster';

type Poster = {
  id: number; template_id: number; template_name: string; created_by: string;
  created_at: string | null; expires_at: string | null; claimed: boolean;
  claimed_at: string | null; customer: string | null; phone_masked: string | null;
  coupon_status: string | null;
};

function dateText(value: string | null) { return formatDateTime(value); }

export default function CouponPosterPanel({ storeId }: { storeId?: number }) {
  const [rows, setRows] = useState<Poster[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [claimed, setClaimed] = useState<boolean | undefined>();
  const [templateId, setTemplateId] = useState<number | undefined>();
  const [templates, setTemplates] = useState<{ value: number; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [preview, setPreview] = useState<{ url: string; posterId: number } | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const { message } = App.useApp();

  useEffect(() => { void getCoupons(storeId).then(r => setTemplates((r.data?.items || []).map((t: any) => ({ value: t.id, label: t.name })))).catch(() => {}); }, [storeId]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    void getCouponPosters({ store_id: storeId, template_id: templateId, claimed, page, page_size: pageSize })
      .then((response) => { if (!active) return; setRows(response.data?.items || []); setTotal(response.data?.total || 0); })
      .catch((failure) => { if (active) { setRows([]); setTotal(0); setError(requestErrorMessage(failure)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, templateId, claimed, page, pageSize, attempt]);

  const openPreview = async (poster: Poster) => {
    setPreviewBusy(true);
    try {
      const response = await getCouponPosterLink(poster.id, storeId);
      const link = response.data?.link;
      if (!link) throw new Error('海报链接缺失');
      const dataUrl = await createCouponPoster(link, getStaff()?.store_name || '本店');
      setPreview({ url: dataUrl, posterId: poster.id });
    } catch (failure) { message.error(requestErrorMessage(failure)); }
    finally { setPreviewBusy(false); }
  };

  const savePreview = () => {
    if (!preview) return;
    const anchor = document.createElement('a');
    anchor.href = preview.url;
    anchor.download = `荷小悦-半价券海报-${preview.posterId}.png`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
  };

  return <div>
    <div className="coupon-panel-head">
      <div><h2>海报记录</h2><p>每张新海报对应一个领取入口；生成不等于发券，打开也不预扣额度。</p></div>
      <Space wrap>
        <Select allowClear placeholder="全部券规则" style={{ width: 200 }} value={templateId} onChange={(value) => { setTemplateId(value); setPage(1); }} options={templates} />
        <Select style={{ width: 130 }} value={claimed === undefined ? 'all' : claimed ? 'claimed' : 'unclaimed'} onChange={(value) => { setClaimed(value === 'all' ? undefined : value === 'claimed'); setPage(1); }} options={[{ value: 'all', label: '全部状态' }, { value: 'claimed', label: '已领取' }, { value: 'unclaimed', label: '未领取' }]} />
        <Button icon={<ReloadOutlined />} onClick={() => setAttempt(v => v + 1)}>刷新</Button>
      </Space>
    </div>
    {error ? <Alert type="error" showIcon message="海报记录加载失败" description={error} action={<Button size="small" onClick={() => setAttempt(v => v + 1)}>重试</Button>} style={{ marginBottom: 12 }} /> : null}
    <Table rowKey="id" size="small" loading={loading} dataSource={rows} scroll={{ x: 850 }}
      pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [20, 50, 100], onChange: (next, size) => { setPage(next); setPageSize(size); } }}
      columns={[
        { title: '生成时间', dataIndex: 'created_at', width: 170, render: dateText },
        { title: '券规则', dataIndex: 'template_name', width: 220, render: (value: string) => <b>{value}</b> },
        { title: '生成人', dataIndex: 'created_by', width: 120 },
        { title: '领取状态', width: 100, render: (_: unknown, row: Poster) => row.claimed ? <Tag color="green">已领取</Tag> : <Tag>未领取</Tag> },
        { title: '顾客', width: 160, render: (_: unknown, row: Poster) => row.claimed ? <span>{row.customer || '—'}<br /><small>{row.phone_masked || ''}</small></span> : '—' },
        { title: '券状态', width: 100, render: (_: unknown, row: Poster) => row.coupon_status ? <Tag color={row.coupon_status === 'used' ? 'green' : row.coupon_status === 'expired' ? 'default' : 'gold'}>{row.coupon_status === 'used' ? '已核销' : row.coupon_status === 'expired' ? '已过期' : row.coupon_status === 'locked' ? '锁定中' : '待使用'}</Tag> : '—' },
        { title: '领取时间', dataIndex: 'claimed_at', width: 170, render: dateText },
        { title: '链接到期', dataIndex: 'expires_at', width: 170, render: dateText },
        { title: '操作', width: 130, render: (_: unknown, row: Poster) => <Button size="small" type="link" icon={<EyeOutlined />} loading={previewBusy} onClick={() => void openPreview(row)}>预览/下载</Button> },
      ]} />
    <Alert style={{ marginTop: 12 }} type="info" showIcon message="再次下载说明"
      description="预览和下载复用同一张海报的领取入口，不新建海报、不新发券，也不生成顾客核销码。海报只用于扫码领取；核销码仍由顾客本人打开券后生成。" />
    <Modal open={Boolean(preview)} onCancel={() => setPreview(null)} footer={<Space><Button onClick={() => setPreview(null)}>关闭</Button><Button type="primary" icon={<DownloadOutlined />} onClick={savePreview}>保存海报</Button></Space>} title="海报预览" width={560}>
      {previewBusy ? <div className="coupon-preview-loading"><Spin /> 正在生成原海报…</div> : preview ? <img className="coupon-poster-preview-image" src={preview.url} alt="荷小悦半价券海报预览" /> : null}
    </Modal>
  </div>;
}
