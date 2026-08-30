import { useEffect, useState } from 'react';
import { App, Button, Form, Space, Switch, Tag } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  ModalForm,
  PageContainer,
  ProForm,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProTable,
  type ActionType,
  type ProColumns,
} from '@ant-design/pro-components';
import { getStaff } from '../api';
import { canManageConfiguration, canManageStoreMasterData, getStoreId } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import MediaUploadField from '../components/MediaUploadField';
import {
  formatProductPrice,
  normalizeProductList,
  PRODUCT_TYPE_LABELS,
  PRODUCT_TYPE_OPTIONS,
  productToForm,
  toProductUpdatePayload,
  toProductPayload,
  type Product,
} from './products-page-model';

const PRODUCT_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  candidate: '待发布',
  published: '已发布',
  inactive: '已下架',
  archived: '已归档',
};

export default function ProductsPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canManage = canManageConfiguration(staff?.role);
  const isHeadquartersAdmin = canManageStoreMasterData(staff?.role, staff?.store_id);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [stores, setStores] = useState<Array<{ id: number; name: string; store_code?: string }>>([]);
  const [form] = Form.useForm();

  useEffect(() => {
    if (!isHeadquartersAdmin) return;
    let active = true;
    refineDataProvider.getList({
      resource: resources.stores,
      pagination: { mode: 'off' },
      filters: [],
      sorters: [],
    }).then((result) => {
      if (active) setStores(result.data as Array<{ id: number; name: string; store_code?: string }>);
    }).catch(() => message.error('门店列表加载失败，请稍后重试'));
    return () => { active = false; };
  }, [isHeadquartersAdmin, message]);

  if (!canManage) {
    return <PageContainer title="商城商品" content="仅管理员或店长可以管理商品。"><div /></PageContainer>;
  }
  if (!isHeadquartersAdmin && !staff?.store_id) {
    return <PageContainer title="商城商品" content="当前账号未绑定门店，请切换到具体门店后管理商品。"><div /></PageContainer>;
  }

  const openEditor = (product?: Product) => {
    setEditing(product || null);
    form.resetFields();
    form.setFieldsValue(product ? productToForm(product) : { product_type: 'foot', price: 9.9, publication_status: 'draft' });
    setOpen(true);
  };

  const togglePublication = async (product: Product, checked: boolean) => {
    try {
      await refineDataProvider.update({
        resource: resources.products,
        id: product.id,
        variables: { publication_status: checked ? 'published' : 'inactive' },
      });
      message.success(checked ? '商品已上架' : '商品已下架');
      actionRef.current?.reload();
    } catch {
      // 统一错误处理器已提示具体原因，保留当前开关状态由表格刷新恢复。
    }
  };

  const columns: ProColumns<Product>[] = [
    { title: '商品编码', dataIndex: 'code', width: 140, copyable: true },
    { title: '商品名称', dataIndex: 'name', width: 180, ellipsis: true },
    {
      title: '分类', dataIndex: 'product_type', width: 100, valueType: 'select',
      valueEnum: Object.fromEntries(PRODUCT_TYPE_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => PRODUCT_TYPE_LABELS[record.product_type] || record.product_type,
    },
    { title: '价格', dataIndex: 'price_cents', width: 100, render: (_, record) => formatProductPrice(record.price_cents) },
    { title: '规格', dataIndex: 'spec', width: 140, ellipsis: true },
    {
      title: '状态', dataIndex: 'publication_status', width: 90, valueType: 'select',
      valueEnum: Object.fromEntries(Object.entries(PRODUCT_STATUS_LABELS).map(([value, text]) => [value, { text }])),
      render: (_, record) => <Tag color={record.publication_status === 'published' ? 'green' : record.publication_status === 'inactive' ? 'red' : 'default'}>{PRODUCT_STATUS_LABELS[record.publication_status] || record.publication_status}</Tag>,
    },
    ...(isHeadquartersAdmin ? [{ title: '门店', dataIndex: 'store_id', width: 110 }] : []),
    {
      title: '操作', valueType: 'option', width: isHeadquartersAdmin ? 110 : 130, fixed: 'right',
      render: (_, record) => isHeadquartersAdmin
        ? <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditor(record)}>编辑</Button>
        : <Space size={8}><span>{record.publication_status === 'published' ? '已上架' : '已下架'}</span><Switch size="small" checked={record.publication_status === 'published'} checkedChildren="上架" unCheckedChildren="下架" onChange={(checked) => togglePublication(record, checked)} /></Space>,
    },
  ];

  return (
    <PageContainer
      title="商城商品"
      content="维护门店可售的泡脚包、热敷和礼盒商品。"
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>,
        ...(isHeadquartersAdmin ? [<Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>新建商品</Button>] : []),
      ]}
    >
      <ProTable<Product>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        search={{ labelWidth: 'auto', defaultCollapsed: true }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        request={async (params) => {
          const storeId = isHeadquartersAdmin ? null : getStoreId(getStaff());
          const result = await refineDataProvider.getList({
            resource: resources.products,
            pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' },
            filters: [
              ...(params.product_type ? [{ field: 'product_type', operator: 'eq' as const, value: params.product_type }] : []),
              ...(params.publication_status ? [{ field: 'status', operator: 'eq' as const, value: params.publication_status }] : []),
            ],
            sorters: [],
          });
          const normalized = normalizeProductList({ data: result.data as Product[], total: result.total });
          const filtered = normalized.data.filter((item) =>
            (!params.product_type || item.product_type === params.product_type)
            && (!params.publication_status || item.publication_status === params.publication_status),
          );
          return { success: true, data: filtered.map((item) => ({ ...item, store_id: item.store_id || storeId || 0 })), total: filtered.length };
        }}
        options={{ density: true, fullScreen: true, reload: true, setting: true }}
        scroll={{ x: 850 }}
      />
      <ModalForm
        key={editing?.id || 'new-product'}
        form={form}
        title={editing ? '编辑商品' : '新建商品'}
        open={open}
        width={560}
        modalProps={{ destroyOnClose: true }}
        onOpenChange={(nextOpen) => { setOpen(nextOpen); if (!nextOpen) { setEditing(null); form.resetFields(); } }}
        onFinish={async (values) => {
          if (editing) {
            await refineDataProvider.update({ resource: resources.products, id: editing.id, variables: toProductUpdatePayload(values) });
            message.success('商品信息已保存');
          } else {
            const storeId = Number(values.store_id);
            await refineDataProvider.create({ resource: resources.products, variables: toProductPayload(values, storeId) });
            message.success('商品已创建');
          }
          actionRef.current?.reload();
          setEditing(null);
          return true;
        }}
      >
        <ProFormText name="code" label="编码" rules={[{ required: true, message: '请输入商品编码' }]} />
        <ProFormText name="name" label="名称" rules={[{ required: true, message: '请输入商品名称' }]} />
        {!editing && <ProFormSelect name="store_id" label="目标门店" options={stores.map((store) => ({ value: store.id, label: `${store.name}${store.store_code ? `（${store.store_code}）` : ''}` }))} rules={[{ required: true, message: '请选择目标门店' }]} />}
        <ProFormSelect name="product_type" label="分类" options={PRODUCT_TYPE_OPTIONS} />
        <ProFormDigit name="price" label="价格（元）" min={0} fieldProps={{ precision: 2, addonBefore: '¥' }} rules={[{ required: true, message: '请输入商品价格' }]} />
        <ProFormText name="spec" label="规格" />
        <ProFormText name="desc" label="说明" />
        <ProForm.Item name="image_url" label="商品图片"><MediaUploadField purpose="product" /></ProForm.Item>
      </ModalForm>
    </PageContainer>
  );
}
