import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Descriptions, Drawer, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { createCoupon, getCoupons, updateCoupon } from '../../api';
import { requestErrorMessage } from '../../requestError';
import { budgetLabel, couponDiscountLabel, formatMoney, percentOffLabel } from '../../utils/couponFormat';

export type CouponTemplate = {
  id: number; code: string; name: string; coupon_type: 'fixed' | 'percent';
  amount_cents: number; percent_off: number | null; min_spend_cents: number;
  validity_days: number; claim_limit: number; budget_cents: number | null;
  committed_cents: number | null; remaining_budget_cents: number | null;
  status: 'draft' | 'published' | 'archived';
  issued_count: number; unused_count: number; locked_count: number; used_count: number; expired_count: number;
  is_claimable: boolean; daily_claimable: boolean; auto_apply: boolean; auto_grant_new_user: boolean;
  config_warnings?: string[];
};

type Props = { storeId?: number; canManage: boolean };

const STATUS_LABEL: Record<string, string> = { draft: '草稿', published: '已上架', archived: '已归档' };
const STATUS_COLOR: Record<string, string> = { draft: 'default', published: 'green', archived: 'orange' };

function statusLabel(value: string) { return STATUS_LABEL[value] || value; }

export default function CouponRulesPanel({ storeId, canManage }: Props) {
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<CouponTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CouponTemplate | null>(null);
  const [detail, setDetail] = useState<CouponTemplate | null>(null);
  const [attempt, setAttempt] = useState(0);
  const loadSeq = useRef(0);

  const load = async () => {
    const seq = ++loadSeq.current;
    setLoading(true); setError('');
    try {
      const response = await getCoupons(storeId);
      if (seq === loadSeq.current) setRows(response.data?.items || []);
    } catch (failure) {
      if (seq === loadSeq.current) { setRows([]); setError(requestErrorMessage(failure)); }
    } finally { if (seq === loadSeq.current) setLoading(false); }
  };
  useEffect(() => { void load(); }, [storeId, attempt]);

  const toggle = async (row: CouponTemplate) => {
    const next = row.status === 'published' ? 'draft' : 'published';
    modal.confirm({
      title: next === 'published' ? '发布这张券？' : '下架这张券？',
      content: next === 'published' ? '发布只影响未来发放和领取，不会改写已发券。' : '下架不会撤销已经发出的券，也不会改变顾客已有权益。',
      okText: next === 'published' ? '发布' : '下架',
      cancelText: '取消',
      onOk: async () => {
        try { await updateCoupon(row.id, { status: next, request_id: crypto.randomUUID() }, storeId); message.success(next === 'published' ? '已上架' : '已下架'); await load(); }
        catch (failure) { message.error(requestErrorMessage(failure)); }
      },
    });
  };

  const columns = [
    { title: '券规则', dataIndex: 'name', width: 220, render: (value: string, row: CouponTemplate) => <div><b>{value}</b><div className="coupon-code">{row.code}</div>{row.config_warnings?.length ? <Tag color="red" style={{ marginTop: 4 }}>配置异常</Tag> : null}</div> },
    { title: '优惠', width: 150, render: (_: unknown, row: CouponTemplate) => <div><b>{couponDiscountLabel(row)}</b><div className="coupon-code">{row.coupon_type === 'percent' ? `减免 ${row.percent_off ?? '—'}%` : '固定面额'}</div></div> },
    { title: '门槛', width: 90, render: (_: unknown, row: CouponTemplate) => row.min_spend_cents > 0 ? `满${formatMoney(row.min_spend_cents)}` : '无门槛' },
    { title: '有效期', width: 80, dataIndex: 'validity_days', render: (value: number) => `${value}天` },
    { title: '预算', width: 170, render: (_: unknown, row: CouponTemplate) => <div>{budgetLabel(row.budget_cents)}<div className="coupon-code">{row.budget_cents === null ? '不限制发放' : `已占 ${formatMoney(row.committed_cents || 0)}`}</div></div> },
    { title: '已发 / 可用', width: 110, render: (_: unknown, row: CouponTemplate) => <div>{row.issued_count} / {row.unused_count}<div className="coupon-code">{row.locked_count ? `锁定 ${row.locked_count}` : `已用 ${row.used_count}`}</div></div> },
    { title: '状态', width: 90, dataIndex: 'status', render: (value: string) => <Tag color={STATUS_COLOR[value]}>{statusLabel(value)}</Tag> },
    { title: '操作', width: 200, render: (_: unknown, row: CouponTemplate) => <Space size={0} wrap>
      <Button size="small" type="link" onClick={() => setDetail(row)}>详情</Button>
      {canManage ? <Button size="small" type="link" icon={<EditOutlined />} onClick={() => { setEditing(row); setEditorOpen(true); }}>编辑</Button> : null}
      {canManage ? <Button size="small" type="link" onClick={() => void toggle(row)}>{row.status === 'published' ? '下架' : '上架'}</Button> : null}
    </Space> },
  ];

  return <div>
    <div className="coupon-panel-head">
      <div><h2>券规则</h2><p>规则治理和发布由管理员操作；店长只在本店发券、核销和查记录。</p></div>
      <Space>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
        {canManage ? <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setEditorOpen(true); }}>新建券</Button> : null}
      </Space>
    </div>
    {error ? <Alert type="error" showIcon message="券规则加载失败" description={error} action={<Button size="small" onClick={() => setAttempt(value => value + 1)}>重试</Button>} style={{ marginBottom: 12 }} /> : null}
    <Table rowKey="id" size="small" loading={loading} dataSource={rows} columns={columns} pagination={false} scroll={{ x: 900 }} />
    <CouponEditor open={editorOpen} template={editing} storeId={storeId} onClose={() => setEditorOpen(false)} onSaved={async () => { setEditorOpen(false); await load(); }} />
    <Drawer title={detail?.name || '券规则详情'} width={520} open={Boolean(detail)} onClose={() => setDetail(null)}>
      {detail ? <div className="coupon-detail">
        {detail.config_warnings?.length ? <Alert type="error" showIcon message="历史配置异常" description={detail.config_warnings.join('；')} style={{ marginBottom: 16 }} /> : null}
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="编码">{detail.code}</Descriptions.Item>
          <Descriptions.Item label="类型">{detail.coupon_type === 'percent' ? '折扣券' : '固定面额券'}</Descriptions.Item>
          <Descriptions.Item label="优惠">{couponDiscountLabel(detail)}{detail.coupon_type === 'percent' ? `（减免 ${detail.percent_off}%）` : ''}</Descriptions.Item>
          <Descriptions.Item label="使用门槛">{detail.min_spend_cents ? `满${formatMoney(detail.min_spend_cents)}` : '无门槛'}</Descriptions.Item>
          <Descriptions.Item label="有效期">领取后 {detail.validity_days} 天</Descriptions.Item>
          <Descriptions.Item label="每人限领">{detail.claim_limit || '不限制'}</Descriptions.Item>
          <Descriptions.Item label="预算">{budgetLabel(detail.budget_cents)}；已占 {formatMoney(detail.committed_cents || 0)}</Descriptions.Item>
          <Descriptions.Item label="当前库存">可用 {detail.unused_count} · 锁定 {detail.locked_count} · 已用 {detail.used_count} · 过期 {detail.expired_count}</Descriptions.Item>
          <Descriptions.Item label="状态">{statusLabel(detail.status)}</Descriptions.Item>
        </Descriptions>
        <div className="coupon-rule-note">
          <p><b>领取方式：</b>{detail.is_claimable ? '领券中心可领' : '当前未开放公开领取'}；{detail.daily_claimable ? '每日可领' : '非每日领取'}；{detail.auto_grant_new_user ? '新客自动发' : '非新客自动发'}。</p>
          <p><b>结算方式：</b>{detail.auto_apply ? '满足条件自动立减' : '需顾客选券或店长发放'}。</p>
          <p><b>历史保护：</b>修改规则不会改写已发券的面额、归属、有效期或历史核销记录。</p>
          <p><b>系统固定规则：</b>半价主项券的适用项目、门店价 5 折和本人绑定由系统契约固定，不在本表单切换。</p>
        </div>
        {canManage ? <Button type="primary" onClick={() => { setEditing(detail); setDetail(null); setEditorOpen(true); }}>编辑规则</Button> : null}
      </div> : null}
    </Drawer>
  </div>;
}

type EditorProps = { open: boolean; template: CouponTemplate | null; storeId?: number; onClose: () => void; onSaved: () => Promise<void> };

function CouponEditor({ open, template, storeId, onClose, onSaved }: EditorProps) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const couponType = Form.useWatch('coupon_type', form) || 'fixed';
  const locked = Boolean(template?.code.startsWith('half-price-50-'));
  const percent = Form.useWatch('percent_off', form);
  const amount = Form.useWatch('amount', form);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue(template ? {
      code: template.code,
      name: template.name,
      coupon_type: template.coupon_type,
      amount: template.coupon_type === 'fixed' ? template.amount_cents / 100 : undefined,
      percent_off: template.percent_off ?? undefined,
      min_spend: template.min_spend_cents / 100,
      validity_days: template.validity_days,
      claim_limit: template.claim_limit,
      budget: template.budget_cents === null ? undefined : template.budget_cents / 100,
      status: template.status === 'archived' ? 'draft' : template.status,
      is_claimable: template.is_claimable,
      daily_claimable: template.daily_claimable,
      auto_apply: template.auto_apply,
      auto_grant_new_user: template.auto_grant_new_user,
    } : {
      coupon_type: 'fixed', amount: undefined, percent_off: undefined,
      min_spend: 0, validity_days: 30, claim_limit: 1, budget: undefined,
      status: 'draft', is_claimable: false, daily_claimable: false,
      auto_apply: false, auto_grant_new_user: false,
    });
  }, [open, template, form]);

  const submit = async (values: any) => {
    if (saving) return;
    setSaving(true);
    try {
      const budget = values.budget === undefined || values.budget === null ? null : Math.round(Number(values.budget) * 100);
      const payload = {
        name: String(values.name || '').trim(),
        coupon_type: values.coupon_type,
        amount_cents: values.coupon_type === 'fixed' ? Math.round(Number(values.amount || 0) * 100) : 0,
        percent_off: values.coupon_type === 'percent' ? Number(values.percent_off) : null,
        min_spend_cents: Math.round(Number(values.min_spend || 0) * 100),
        validity_days: Number(values.validity_days),
        claim_limit: Number(values.claim_limit || 0),
        budget_cents: budget,
        status: values.status,
        is_claimable: Boolean(values.is_claimable),
        daily_claimable: Boolean(values.daily_claimable),
        auto_apply: Boolean(values.auto_apply),
        auto_grant_new_user: Boolean(values.auto_grant_new_user),
        request_id: crypto.randomUUID(),
      };
      if (template) await updateCoupon(template.id, payload, storeId);
      else await createCoupon({ ...payload, code: String(values.code || '').trim() }, storeId);
      message.success(template ? '规则已保存' : '草稿已创建');
      await onSaved();
    } catch (failure) {
      message.error(requestErrorMessage(failure));
    } finally { setSaving(false); }
  };

  return <Modal open={open} onCancel={onClose} footer={null} width={620} title={template ? '编辑券规则' : '新建券规则'} destroyOnClose>
    <Form form={form} layout="vertical" onFinish={submit}>
      {locked ? <Alert type="warning" showIcon message="这是系统半价主项券" description="类型、优惠、门槛和有效期由半价券契约固定；可维护名称、预算和状态。适用项目不在后台切换。" style={{ marginBottom: 12 }} /> : null}
      <div className="coupon-form-grid">
        <Form.Item name="code" label="编码" rules={[{ required: true, message: '请填写编码' }, { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/, message: '字母、数字、点、横线或下划线，1-32 位' }]}>
          <Input disabled={Boolean(template)} placeholder="例如 full-100-20" />
        </Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}><Input maxLength={64} placeholder="例如 满100减20" /></Form.Item>
      </div>
      <div className="coupon-form-grid">
        <Form.Item name="coupon_type" label="类型" rules={[{ required: true }]}><Select disabled={locked} options={[{ value: 'fixed', label: '固定面额券' }, { value: 'percent', label: '折扣券' }]} /></Form.Item>
        {couponType === 'fixed' ? <Form.Item name="amount" label="面额（元）" rules={[{ required: true, message: '请填写面额' }]}>
          <InputNumber disabled={locked} min={0.01} precision={2} style={{ width: '100%' }} placeholder="例如 20" />
        </Form.Item> : <Form.Item name="percent_off" label="减免比例（%）" tooltip="20 表示减免 20%，即 8 折；不是 2 折" rules={[{ required: true, message: '请填写减免比例' }]}>
          <InputNumber disabled={locked} min={1} max={100} precision={0} style={{ width: '100%' }} placeholder="例如 20" />
        </Form.Item>}
      </div>
      <div className="coupon-form-grid">
        <Form.Item name="min_spend" label="使用门槛（元）"><InputNumber disabled={locked} min={0} precision={2} style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="validity_days" label="领取后有效期（天）"><InputNumber disabled={locked} min={1} max={3650} precision={0} style={{ width: '100%' }} /></Form.Item>
      </div>
      <div className="coupon-form-grid">
        <Form.Item name="budget" label="预算（元）" tooltip="留空表示不限；填 0 表示零预算。固定面额券按全部已发券数量×面额占用预算，不随核销或过期释放。">
          <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="留空=不限；0=零预算" />
        </Form.Item>
        <Form.Item name="claim_limit" label="每人限领" tooltip="0 表示不限制"><InputNumber min={0} precision={0} style={{ width: '100%' }} /></Form.Item>
      </div>
      <Form.Item name="status" label="状态" extra="建议先保存草稿并核对规则，再发布。发布只影响未来发放和领取。">
        <Select options={[{ value: 'draft', label: '草稿' }, { value: 'published', label: '已上架' }]} />
      </Form.Item>
      <div className="coupon-checks">
        <Form.Item name="is_claimable" valuePropName="checked"><Switch size="small" /> 领券中心可领</Form.Item>
        <Form.Item name="daily_claimable" valuePropName="checked"><Switch size="small" /> 每日可领</Form.Item>
        <Form.Item name="auto_apply" valuePropName="checked"><Switch size="small" /> 自动立减</Form.Item>
        <Form.Item name="auto_grant_new_user" valuePropName="checked"><Switch size="small" /> 新客自动发</Form.Item>
      </div>
      <div className="coupon-preview">
        <p className="coupon-kicker">规则预览</p>
        <strong>{couponType === 'percent' ? `减免 ${percent || 0}% · ${percentOffLabel(Number(percent || 0))}` : `固定面额 ${formatMoney(Math.round(Number(amount || 0) * 100))}`}</strong>
        <p>{couponType === 'percent' ? '按订单金额比例减免，不改变会员价规则。' : '满足门槛后按固定金额减免。'}</p>
        <small>预算：{form.getFieldValue('budget') === undefined ? '不限' : budgetLabel(Math.round(Number(form.getFieldValue('budget') || 0) * 100))} · 发布后不会改写已发券。</small>
      </div>
      <div className="coupon-editor-actions">
        <Button onClick={onClose} disabled={saving}>取消</Button>
        <Button type="primary" htmlType="submit" loading={saving} disabled={saving}>保存</Button>
      </div>
    </Form>
  </Modal>;
}
