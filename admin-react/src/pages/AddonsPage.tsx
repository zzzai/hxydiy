import { useEffect, useRef, useState } from 'react';
import { App, Button, Form, Popconfirm, Space, Switch, Tag } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { ModalForm, PageContainer, ProFormDigit, ProFormSelect, ProFormText, ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { getProjectsAdmin, getStaff } from '../api';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import MediaUploadField from '../components/MediaUploadField';
import { addonFormPayload } from '../addonContent';
import { ADDON_STATUS_OPTIONS, addonCreateStoreId, addonStatusColor, addonStatusLabel, canEditAddonMasterData, canStoreToggleAddon, canViewAddons, normalizeAddonList, validateAddonPrices, type Addon } from './addon-page-model';

const money = (cents?: number | null) => `¥${(Number(cents || 0) / 100).toFixed(2)}`;

export default function AddonsPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canView = canViewAddons(staff?.role);
  const isHeadquartersAdmin = canEditAddonMasterData(staff?.role, staff?.store_id);
  const actionRef = useRef<ActionType>();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Addon | null>(null);
  const [projects, setProjects] = useState<Array<{ id: number; name: string }>>([]);
  const [stores, setStores] = useState<Array<{ id: number; name: string; store_code?: string }>>([]);
  const [form] = Form.useForm();
  const chargeable = Form.useWatch('chargeable', form);
  const memberPriceEnabled = Form.useWatch('member_price_enabled', form);
  const targetStoreId = Form.useWatch('store_id', form);

  useEffect(() => {
    if (!canView) return;
    void getProjectsAdmin().then((result) => setProjects(result.data || [])).catch(() => message.error('项目列表加载失败，请稍后重试'));
    if (isHeadquartersAdmin) void refineDataProvider.getList({ resource: resources.stores, pagination: { currentPage: 1, pageSize: 100, mode: 'server' }, filters: [], sorters: [] }).then((result) => setStores(result.data as typeof stores)).catch(() => message.error('门店列表加载失败，请稍后重试'));
  }, [canView, isHeadquartersAdmin, message]);

  if (!canView) return <PageContainer title="项目加项" content="仅管理员或店长可以查看项目加项。"><div /></PageContainer>;
  if (!isHeadquartersAdmin && !staff?.store_id) return <PageContainer title="项目加项" content="当前账号未绑定门店，无法查看加项。"><div /></PageContainer>;

  const openEditor = (addon?: Addon) => {
    setEditing(addon || null); form.resetFields();
    form.setFieldsValue(addon ? { ...addon, store_price: Number(addon.store_price_cents || 0) / 100, member_price: addon.member_price_enabled ? Number(addon.member_price_cents || 0) / 100 : null } : { chargeable: true, can_attach_to_parent: true, independently_sellable: false, member_price_enabled: false, publication_status: 'draft', display_order: 0, store_price: 0 });
    setOpen(true);
  };
  const updatePublication = async (addon: Addon, checked: boolean) => {
    try { await refineDataProvider.update({ resource: resources.addons, id: addon.id, variables: { publication_status: checked ? 'published' : 'inactive' } }); message.success(checked ? '加项已上架' : '加项已下架'); actionRef.current?.reload(); } catch { /* 统一错误处理器已提示服务端原因 */ }
  };
  const columns: ProColumns<Addon>[] = [
    { title: '加项编码', dataIndex: 'code', width: 140, copyable: true },
    { title: '名称', dataIndex: 'name', width: 190, ellipsis: true, render: (_, row) => <Space direction="vertical" size={0}><strong>{row.name}</strong><span style={{ color: '#84938f', fontSize: 12 }}>{row.summary || '暂无简介'}</span></Space> },
    { title: '关联主项', dataIndex: 'parent_project_id', width: 150, render: (_, row) => projects.find((project) => project.id === row.parent_project_id)?.name || '仅独立售卖' },
    { title: '收费规则', width: 200, render: (_, row) => row.chargeable ? <Space size={4} wrap><Tag>门店 {money(row.store_price_cents)}</Tag>{row.member_price_enabled && <Tag color="green">会员 {money(row.member_price_cents)}</Tag>}</Space> : <Tag>免费偏好</Tag> },
    { title: '可选方式', width: 150, render: (_, row) => <Space size={4} wrap>{row.can_attach_to_parent && <Tag color="blue">随主项加购</Tag>}{row.independently_sellable && <Tag color="purple">可单独售卖</Tag>}</Space> },
    { title: '状态', dataIndex: 'publication_status', width: 110, valueType: 'select', valueEnum: Object.fromEntries(ADDON_STATUS_OPTIONS.map((item) => [item.value, { text: item.label }])), render: (_, row) => <Tag color={addonStatusColor(row.publication_status)}>{addonStatusLabel(row.publication_status)}</Tag> },
    ...(isHeadquartersAdmin ? [{ title: '门店', dataIndex: 'store_id', width: 90 }] : []),
    { title: '操作', valueType: 'option', width: isHeadquartersAdmin ? 180 : 170, fixed: 'right', render: (_, row) => isHeadquartersAdmin ? <Space size={4}><Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditor(row)}>编辑</Button>{row.publication_status !== 'archived' && <Popconfirm title="确定强制下线该加项吗？店长不能恢复。" onConfirm={() => refineDataProvider.update({ resource: resources.addons, id: row.id, variables: { publication_status: 'archived' } }).then(() => { message.success('加项已强制下线'); actionRef.current?.reload(); })}><Button size="small" type="link" danger>强制下线</Button></Popconfirm>}</Space> : <Space size={8}><span>{row.publication_status === 'published' ? '已上架' : '未上架'}</span><Switch size="small" disabled={!canStoreToggleAddon(row.publication_status)} checked={row.publication_status === 'published'} checkedChildren="上架" unCheckedChildren="下架" onChange={(checked) => updatePublication(row, checked)} /></Space> },
  ];
  return <PageContainer title="项目加项" content="维护服务项目的可选加项、价格与门店上架状态。" extra={[<Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>, ...(isHeadquartersAdmin ? [<Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>新建加项</Button>] : [])]}>
    <ProTable<Addon> actionRef={actionRef} rowKey="id" columns={columns} search={{ labelWidth: 'auto', defaultCollapsed: true }} pagination={{ defaultPageSize: 20, showSizeChanger: true }} request={async (params) => { const result = await refineDataProvider.getList({ resource: resources.addons, pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' }, filters: params.publication_status ? [{ field: 'status', operator: 'eq' as const, value: params.publication_status }] : [], sorters: [] }); const normalized = normalizeAddonList({ data: result.data, total: result.total }); return { success: true, data: normalized.data, total: result.total }; }} options={{ density: true, fullScreen: true, reload: true, setting: true }} scroll={{ x: 1100 }} />
    <ModalForm key={editing?.id || 'new-addon'} form={form} title={editing ? '编辑项目加项' : '新建项目加项'} open={open} width={720} modalProps={{ destroyOnClose: true }} onOpenChange={(nextOpen) => { setOpen(nextOpen); if (!nextOpen) { setEditing(null); form.resetFields(); } }} onFinish={async (values) => { const priceError = validateAddonPrices(values); if (priceError) { message.error(priceError); return false; } try { const payload = addonFormPayload(values); if (editing) { await refineDataProvider.update({ resource: resources.addons, id: editing.id, variables: payload }); message.success('加项已保存'); } else { const storeId = addonCreateStoreId(staff?.role, staff?.store_id, values.store_id); await refineDataProvider.create({ resource: resources.addons, variables: { ...payload, store_id: storeId } }); message.success('加项已创建'); } actionRef.current?.reload(); setEditing(null); return true; } catch (error) { message.error(error instanceof Error ? error.message : '保存失败，请稍后重试'); return false; } }}>
      {!editing && isHeadquartersAdmin && <ProFormSelect name="store_id" label="目标门店" options={stores.map((store) => ({ value: store.id, label: `${store.name}${store.store_code ? `（${store.store_code}）` : ''}` }))} rules={[{ required: true, message: '请选择目标门店' }]} />}
      <Space wrap><ProFormText name="code" label="编码" rules={[{ required: true, message: '请填写编码' }]} disabled={!!editing} /><ProFormText name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]} /></Space>
      <ProFormSelect name="parent_project_id" label="关联主项目" options={projects.map((project) => ({ value: project.id, label: project.name }))} allowClear placeholder="仅独立售卖时可不选" />
      <Space wrap><ProFormDigit name="duration_min" label="时长（分）" min={0} /><ProFormDigit name="display_order" label="展示顺序" min={0} /><ProFormSelect name="publication_status" label="状态" options={ADDON_STATUS_OPTIONS.map((item) => ({ value: item.value, label: item.label }))} /></Space>
      <Space wrap><Form.Item name="chargeable" label="是否收费" valuePropName="checked"><Switch checkedChildren="收费" unCheckedChildren="免费" /></Form.Item><Form.Item name="can_attach_to_parent" label="随主项目加购" valuePropName="checked"><Switch /></Form.Item><Form.Item name="independently_sellable" label="可单独售卖" valuePropName="checked"><Switch /></Form.Item></Space>
      {chargeable !== false && <Space wrap><ProFormDigit name="store_price" label="门店价（元）" min={0} fieldProps={{ precision: 2 }} rules={[{ required: true, message: '请填写门店价' }]} /><Form.Item name="member_price_enabled" label="启用会员价" valuePropName="checked"><Switch /></Form.Item>{memberPriceEnabled && <ProFormDigit name="member_price" label="会员价（元）" min={0} fieldProps={{ precision: 2 }} rules={[{ required: true, message: '请填写会员价' }]} />}</Space>}
      <ProFormText name="summary" label="简介" fieldProps={{ maxLength: 512 }} /><Form.Item name="image_url" label="图片"><MediaUploadField purpose="addon" storeId={editing?.store_id || targetStoreId} requireStoreId={isHeadquartersAdmin} /></Form.Item>
    </ModalForm>
  </PageContainer>;
}
