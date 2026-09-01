import { useEffect, useMemo, useState } from 'react';
import { App, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag } from 'antd';
import { EditOutlined, PlusOutlined } from '@ant-design/icons';
import { createAddon, getAddonsAdmin, getProjectsAdmin, getStaff, updateAddon } from '../api';
import { addonFormPayload, addonToForm } from '../addonContent';
import { getStoreId } from '../auth';

const STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'candidate', label: '待审核' },
  { value: 'published', label: '已发布' },
  { value: 'archived', label: '已停用' },
];

const money = (cents?: number) => `¥${(Number(cents || 0) / 100).toFixed(2)}`;

export default function AddonsPage() {
  const { message } = App.useApp();
  const [addons, setAddons] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [form] = Form.useForm();
  const chargeable = Form.useWatch('chargeable', form);
  const memberPriceEnabled = Form.useWatch('member_price_enabled', form);

  const projectOptions = useMemo(
    () => projects.map((project) => ({ value: project.id, label: project.name })),
    [projects],
  );

  const load = async () => {
    setLoading(true);
    try {
      const [addonResponse, projectResponse] = await Promise.all([getAddonsAdmin(), getProjectsAdmin()]);
      setAddons(addonResponse.data || []);
      setProjects(projectResponse.data || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openEditor = (addon?: any) => {
    setEditing(addon || null);
    form.resetFields();
    form.setFieldsValue(addon ? addonToForm(addon) : {
      chargeable: true,
      can_attach_to_parent: true,
      independently_sellable: false,
      member_price_enabled: false,
      publication_status: 'draft',
      display_order: 0,
      store_price: 0,
    });
    setOpen(true);
  };

  const save = async (values: any) => {
    let storeId: number;
    try {
      storeId = getStoreId(getStaff());
    } catch (error) {
      message.error(error instanceof Error ? error.message : '当前账号未绑定门店');
      return;
    }
    const payload = addonFormPayload(values);
    if (payload.member_price_enabled && (payload.member_price_cents === null || payload.member_price_cents < 0)) {
      message.error('启用会员价时请填写会员价');
      return;
    }
    if (editing) {
      await updateAddon(editing.id, payload);
      message.success('加项已保存');
    } else {
      await createAddon({ ...payload, store_id: storeId });
      message.success('加项已创建');
    }
    setOpen(false);
    setEditing(null);
    form.resetFields();
    load();
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontWeight: 600 }}>项目加项管理</span>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>新建加项</Button>
      </div>
      <Table
        dataSource={addons}
        loading={loading}
        rowKey="id"
        size="small"
        pagination={false}
        columns={[
          { title: '名称', dataIndex: 'name', render: (name: string, row: any) => <><b>{name}</b><br /><span style={{ color: '#84938f', fontSize: 12 }}>{row.summary || row.code}</span></> },
          { title: '关联主项', dataIndex: 'parent_project_id', render: (id: number | null) => projects.find((project) => project.id === id)?.name || '仅独立售卖' },
          { title: '收费规则', width: 200, render: (_: unknown, row: any) => row.chargeable ? <Space size={4} wrap><Tag>门店 {money(row.store_price_cents)}</Tag>{row.member_price_enabled && <Tag color="green">会员 {money(row.member_price_cents)}</Tag>}</Space> : <Tag>免费偏好</Tag> },
          { title: '可选方式', width: 140, render: (_: unknown, row: any) => <Space size={4} wrap>{row.can_attach_to_parent && <Tag color="blue">随主项加购</Tag>}{row.independently_sellable && <Tag color="purple">可单独售卖</Tag>}</Space> },
          { title: '状态', dataIndex: 'publication_status', width: 90, render: (status: string) => <Tag color={status === 'published' ? 'green' : status === 'archived' ? 'default' : 'gold'}>{STATUS_OPTIONS.find((item) => item.value === status)?.label || status}</Tag> },
          { title: '操作', width: 84, render: (_: unknown, row: any) => <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(row)}>编辑</Button> },
        ]}
      />
      <Modal open={open} onCancel={() => { setOpen(false); setEditing(null); }} title={editing ? '编辑项目加项' : '新建项目加项'} footer={null} width={720} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={save}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Space wrap>
              <Form.Item name="code" label="编码" rules={[{ required: true, message: '请填写编码' }]}><Input disabled={!!editing} /></Form.Item>
              <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}><Input /></Form.Item>
              <Form.Item name="parent_project_id" label="关联主项目"><Select allowClear placeholder="仅独立售卖时可不选" options={projectOptions} style={{ minWidth: 180 }} /></Form.Item>
            </Space>
            <Space wrap>
              <Form.Item name="duration_min" label="时长(分)"><InputNumber min={0} /></Form.Item>
              <Form.Item name="display_order" label="展示顺序"><InputNumber min={0} /></Form.Item>
              <Form.Item name="publication_status" label="状态"><Select options={STATUS_OPTIONS} style={{ width: 120 }} /></Form.Item>
            </Space>
            <Space wrap>
              <Form.Item name="chargeable" label="是否收费" valuePropName="checked"><Switch checkedChildren="收费" unCheckedChildren="免费" /></Form.Item>
              <Form.Item name="can_attach_to_parent" label="随主项目加购" valuePropName="checked"><Switch /></Form.Item>
              <Form.Item name="independently_sellable" label="可单独售卖" valuePropName="checked"><Switch /></Form.Item>
            </Space>
            {chargeable !== false && <>
              <Space wrap>
                <Form.Item name="store_price" label="门店价(元)" rules={[{ required: true, message: '请填写门店价' }]}><InputNumber min={0} precision={2} /></Form.Item>
                <Form.Item name="member_price_enabled" label="启用会员价" valuePropName="checked"><Switch /></Form.Item>
                {memberPriceEnabled && <Form.Item name="member_price" label="会员价(元)" rules={[{ required: true, message: '请填写会员价' }]}><InputNumber min={0} precision={2} /></Form.Item>}
              </Space>
            </>}
            <Form.Item name="summary" label="简介"><Input.TextArea rows={2} maxLength={512} /></Form.Item>
            <Form.Item name="image_url" label="图片地址"><Input /></Form.Item>
            <Button type="primary" htmlType="submit" block>保存</Button>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
