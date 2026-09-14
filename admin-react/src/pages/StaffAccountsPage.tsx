import { useEffect, useState } from 'react';
import { App, Button, Tag } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { ModalForm, PageContainer, ProFormGroup, ProFormSelect, ProFormText, ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { getStaff, getStoreMasterData } from '../api';
import { canManageStoreMasterData } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import {
  getStaffAccountRoleMeta,
  getStaffAccountStatusMeta,
  staffAccountPayload,
  type StaffAccount,
  type StaffAccountForm,
  type StaffAccountRole,
  type StaffAccountStatus,
} from './staff-accounts-page-model';

type StoreOption = { id: number; name: string; store_code?: string };

const roleOptions = [
  { value: 'manager', label: '店长' },
  { value: 'staff', label: '门店员工' },
];
const statusOptions = [
  { value: 'active', label: '在职可登录' },
  { value: 'disabled', label: '已停用' },
];

export default function StaffAccountsPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canManage = canManageStoreMasterData(staff?.role, staff?.store_id);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<StaffAccount | null>(null);
  const [stores, setStores] = useState<StoreOption[]>([]);

  useEffect(() => {
    if (!canManage) return;
    getStoreMasterData({ page: 1, page_size: 100 })
      .then((response) => setStores(response.data.items || response.data || []))
      .catch(() => undefined);
  }, [canManage]);

  if (!canManage) {
    return <PageContainer title="员工账号" content="仅总部管理员可以管理门店员工和店长的登录账号。"><div /></PageContainer>;
  }

  const columns: ProColumns<StaffAccount>[] = [
    { title: '登录名', dataIndex: 'username', width: 150, copyable: true },
    { title: '姓名', dataIndex: 'name', width: 120 },
    {
      title: '角色', dataIndex: 'role', width: 120, valueType: 'select',
      valueEnum: Object.fromEntries(roleOptions.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => { const meta = getStaffAccountRoleMeta(record.role); return <Tag color={meta.color}>{meta.label}</Tag>; },
    },
    {
      title: '所属门店', dataIndex: 'store_id', width: 180,
      render: (_, record) => stores.find((store) => store.id === record.store_id)?.name || `门店 #${record.store_id}`,
    },
    {
      title: '账号状态', dataIndex: 'status', width: 130, valueType: 'select',
      valueEnum: Object.fromEntries(statusOptions.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => { const meta = getStaffAccountStatusMeta(record.status); return <Tag color={meta.color}>{meta.label}</Tag>; },
    },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime', hideInSearch: true },
    { title: '操作', valueType: 'option', width: 80, render: (_, record) => [<Button key="edit" type="link" onClick={() => { setEditing(record); setOpen(true); }}>编辑</Button>] },
  ];

  return <PageContainer
    title="员工账号"
    content="总部统一维护在职门店员工和店长账号；调岗、停用或重置密码会撤销原登录会话。技师账号请在技师管理中维护。"
    extra={[
      <Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>,
      <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setOpen(true); }}>新建账号</Button>,
    ]}
  >
    <ProTable<StaffAccount>
      actionRef={actionRef}
      rowKey="id"
      columns={columns}
      search={{ labelWidth: 'auto', defaultCollapsed: true }}
      pagination={{ defaultPageSize: 20, showSizeChanger: true }}
      request={async (params) => {
        const result = await refineDataProvider.getList({
          resource: resources.staffAccounts,
          pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' },
          filters: [
            { field: 'status', operator: 'eq', value: params.status },
            { field: 'store_id', operator: 'eq', value: params.store_id },
          ],
          sorters: [],
        });
        return { success: true, data: result.data as StaffAccount[], total: result.total };
      }}
      options={{ density: true, fullScreen: true, reload: true, setting: true }}
      scroll={{ x: 1000 }}
    />
    <ModalForm<StaffAccountForm>
      key={editing?.id || 'new-staff-account'}
      title={editing ? '编辑员工账号' : '新建员工账号'}
      open={open}
      width={560}
      modalProps={{ destroyOnClose: true, onCancel: () => setEditing(null) }}
      initialValues={editing || { role: 'staff' as StaffAccountRole, status: 'active' as StaffAccountStatus }}
      onOpenChange={(nextOpen) => { setOpen(nextOpen); if (!nextOpen) setEditing(null); }}
      onFinish={async (values) => {
        const payload = staffAccountPayload(values, !!editing);
        if (editing) {
          await refineDataProvider.update({ resource: resources.staffAccounts, id: editing.id, variables: payload });
          message.success('员工账号已更新，原登录会话已按变更规则撤销');
        } else {
          await refineDataProvider.create({ resource: resources.staffAccounts, variables: payload });
          message.success('员工账号已创建');
        }
        actionRef.current?.reload();
        setEditing(null);
        return true;
      }}
    >
      <ProFormGroup>
        <ProFormText name="username" label="登录名" width="md" disabled={!!editing} rules={[{ required: !editing, message: '请输入登录名' }, { pattern: /^[A-Za-z0-9_.-]+$/, message: '仅支持字母、数字、点、下划线和连字符' }]} />
        <ProFormText name="name" label="姓名" width="md" rules={[{ required: true, message: '请输入姓名' }]} />
      </ProFormGroup>
      <ProFormText name="password" label={editing ? '重置密码' : '初始密码'} fieldProps={{ type: 'password', autoComplete: 'new-password' }} rules={[{ required: !editing, message: '请输入至少 8 位初始密码' }, { min: 8, message: '密码至少 8 位' }]} extra={editing ? '留空则不修改密码；填写后原登录会话会立即失效。' : undefined} />
      <ProFormGroup>
        <ProFormSelect name="role" label="角色" width="md" options={roleOptions} rules={[{ required: true, message: '请选择角色' }]} />
        <ProFormSelect name="status" label="账号状态" width="md" options={statusOptions} rules={[{ required: true, message: '请选择账号状态' }]} />
      </ProFormGroup>
      <ProFormSelect name="store_id" label="所属门店" options={stores.map((store) => ({ value: store.id, label: `${store.name}${store.store_code ? `（${store.store_code}）` : ''}` }))} rules={[{ required: true, message: '请选择所属门店' }]} />
    </ModalForm>
  </PageContainer>;
}
