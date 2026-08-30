import { useState } from 'react';
import { App, Button, Tag } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
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
import { canManageConfiguration, getStoreId } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import MediaUploadField from '../components/MediaUploadField';
import {
  formatProductPrice,
  normalizeProductList,
  PRODUCT_TYPE_LABELS,
  PRODUCT_TYPE_OPTIONS,
  toProductPayload,
  type Product,
} from './products-page-model';

export default function ProductsPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canManage = canManageConfiguration(staff?.role);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);

  if (!canManage) {
    return <PageContainer title="商城商品" content="仅管理员或店长可以管理商品。"><div /></PageContainer>;
  }
  if (!staff?.store_id) {
    return <PageContainer title="商城商品" content="当前账号未绑定门店，请切换到具体门店后管理商品。"><div /></PageContainer>;
  }

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
      valueEnum: { published: { text: '已发布' }, draft: { text: '草稿' } },
      render: (_, record) => <Tag color={record.publication_status === 'published' ? 'green' : 'default'}>{record.publication_status === 'published' ? '已发布' : '草稿'}</Tag>,
    },
  ];

  return (
    <PageContainer
      title="商城商品"
      content="维护门店可售的泡脚包、热敷和礼盒商品。"
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>,
        <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新建商品</Button>,
      ]}
    >
      <ProTable<Product>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        search={{ labelWidth: 'auto', defaultCollapsed: true }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        request={async (params) => {
          const storeId = getStoreId(getStaff());
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
          return { success: true, data: filtered.map((item) => ({ ...item, store_id: item.store_id || storeId })), total: filtered.length };
        }}
        options={{ density: true, fullScreen: true, reload: true, setting: true }}
        scroll={{ x: 850 }}
      />
      <ModalForm
        title="新建商品"
        open={open}
        width={560}
        modalProps={{ destroyOnClose: true }}
        onOpenChange={setOpen}
        initialValues={{ product_type: 'foot', price: 9.9, publication_status: 'draft' }}
        onFinish={async (values) => {
          const storeId = getStoreId(getStaff());
          await refineDataProvider.create({ resource: resources.products, variables: toProductPayload(values, storeId) });
          message.success('商品已创建');
          actionRef.current?.reload();
          return true;
        }}
      >
        <ProFormText name="code" label="编码" rules={[{ required: true, message: '请输入商品编码' }]} />
        <ProFormText name="name" label="名称" rules={[{ required: true, message: '请输入商品名称' }]} />
        <ProFormSelect name="product_type" label="分类" options={PRODUCT_TYPE_OPTIONS} />
        <ProFormDigit name="price" label="价格（元）" min={0} fieldProps={{ precision: 2, addonBefore: '¥' }} rules={[{ required: true, message: '请输入商品价格' }]} />
        <ProFormText name="spec" label="规格" />
        <ProFormText name="desc" label="说明" />
        <ProForm.Item name="image_url" label="商品图片"><MediaUploadField purpose="product" /></ProForm.Item>
      </ModalForm>
    </PageContainer>
  );
}
