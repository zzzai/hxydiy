import { useState } from 'react';
import { Alert, App, Button, List, Modal, Tag } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { ModalForm, PageContainer, ProFormGroup, ProFormSelect, ProFormText, ProFormTextArea, ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { getStaff, getStoreOpeningCheck } from '../api';
import { canManageStoreMasterData } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import { STORE_STATUS_OPTIONS, getStoreStatusMeta, getStoreStatusOptions, normalizeStoreList, type Store, type StoreStatus } from './stores-page-model';

export default function StoresPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canManage = canManageStoreMasterData(staff?.role, staff?.store_id);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Store | null>(null);
  const [checking, setChecking] = useState<Store | null>(null);
  const [openingCheck, setOpeningCheck] = useState<{ ready: boolean; checks: { key: string; label: string; passed: boolean; detail: string }[] }>();
  const [checkLoading, setCheckLoading] = useState(false);

  const showOpeningCheck = async (store: Store) => {
    setChecking(store);
    setOpeningCheck(undefined);
    setCheckLoading(true);
    try {
      const response = await getStoreOpeningCheck(store.id);
      setOpeningCheck(response.data);
    } catch {
      message.error('开业检查加载失败，请稍后重试');
    } finally {
      setCheckLoading(false);
    }
  };

  if (!canManage) {
    return <PageContainer title="门店主数据" content="仅总部管理员可以管理门店。"><div /></PageContainer>;
  }

  const columns: ProColumns<Store>[] = [
    { title: '门店编码', dataIndex: 'store_code', width: 140, copyable: true },
    { title: '门店名称', dataIndex: 'name', width: 180, ellipsis: true },
    { title: '城市', dataIndex: 'city', width: 100 },
    { title: '地址', dataIndex: 'address', ellipsis: true },
    { title: '联系电话', dataIndex: 'phone', width: 140 },
    { title: '营业时间', dataIndex: 'business_hours', width: 130 },
    {
      title: '状态', dataIndex: 'status', width: 100, valueType: 'select',
      valueEnum: Object.fromEntries(STORE_STATUS_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => { const meta = getStoreStatusMeta(record.status); return <Tag color={meta.color}>{meta.label}</Tag>; },
    },
    { title: '操作', valueType: 'option', width: 190, render: (_, record) => [
      <Button key="check" type="link" onClick={() => void showOpeningCheck(record)}>开业检查</Button>,
      <Button key="edit" type="link" onClick={() => { setEditing(record); setOpen(true); }}>编辑</Button>,
    ] },
  ];

  return (
    <PageContainer
      title="门店主数据"
      content="统一维护门店编码、营业状态和顾客入口归属。"
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>,
        <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setOpen(true); }}>新建门店</Button>,
      ]}
    >
      <ProTable<Store>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        search={{ labelWidth: 'auto', defaultCollapsed: true }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        request={async (params) => {
          const result = await refineDataProvider.getList({
            resource: resources.stores,
            pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' },
            filters: params.status ? [{ field: 'status', operator: 'eq', value: params.status }] : [],
            sorters: [],
          });
          const normalized = normalizeStoreList({ data: result.data as Store[], total: result.total });
          return { ...normalized, success: true };
        }}
        options={{ density: true, fullScreen: true, reload: true, setting: true }}
        scroll={{ x: 1050 }}
      />
      <ModalForm<Store>
        title={editing ? '编辑门店' : '新建门店'} open={open} width={560}
        modalProps={{ destroyOnClose: true, onCancel: () => setEditing(null) }}
        initialValues={editing || { status: 'preparing' as StoreStatus }}
        onOpenChange={(nextOpen) => { setOpen(nextOpen); if (!nextOpen) setEditing(null); }}
        onFinish={async (values) => {
          try {
            if (editing) {
              await refineDataProvider.update({ resource: resources.stores, id: editing.id, variables: values });
              message.success('门店信息已更新');
            } else {
              await refineDataProvider.create({ resource: resources.stores, variables: values });
              message.success('门店已创建');
            }
          } catch (error: any) {
            const detail = error?.response?.data?.detail;
            message.error(detail?.message || '门店保存失败');
            return false;
          }
          actionRef.current?.reload(); setEditing(null); return true;
        }}
      >
        <ProFormGroup>
          <ProFormText name="store_code" label="门店编码" width="md" disabled={!!editing} rules={[{ required: !editing, message: '请输入门店编码' }]} placeholder="例如 store-01" />
          <ProFormText name="name" label="门店名称" width="md" rules={[{ required: true, message: '请输入门店名称' }]} />
        </ProFormGroup>
        <ProFormGroup>
          <ProFormText name="city" label="城市" width="md" />
          <ProFormText name="phone" label="联系电话" width="md" />
        </ProFormGroup>
        <ProFormText name="address" label="地址" rules={[{ required: true, message: '请输入门店地址' }]} />
        <ProFormText name="business_hours" label="营业时间" placeholder="10:00-22:00" />
        <ProFormSelect
          name="status"
          label="营业状态"
          options={getStoreStatusOptions(editing?.status)}
          extra={editing ? '只显示当前状态允许进入的下一状态；停业前系统会检查未完成订单和服务位占用。' : '新门店建议先保存为筹备中。'}
        />
        {editing && <ProFormTextArea name="reason" label="状态/资料变更原因" placeholder="例如：完成开业准备，进入试营业" maxLength={200} />}
      </ModalForm>
      <Modal
        title={`开业检查 · ${checking?.name || ''}`}
        open={Boolean(checking)}
        onCancel={() => setChecking(null)}
        footer={<Button onClick={() => setChecking(null)}>关闭</Button>}
        loading={checkLoading}
      >
        {openingCheck && <>
          <Alert
            type={openingCheck.ready ? 'success' : 'warning'}
            showIcon
            message={openingCheck.ready ? '已满足当前开业检查条件' : '还有未完成项，暂不能切换到营业中'}
            style={{ marginBottom: 12 }}
          />
          <List
            size="small"
            dataSource={openingCheck.checks}
            renderItem={(item) => <List.Item>{item.passed ? '✅' : '⚠️'} {item.label}：{item.detail}</List.Item>}
          />
        </>}
      </Modal>
    </PageContainer>
  );
}
