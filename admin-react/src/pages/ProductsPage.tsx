import { useEffect, useState } from 'react';
import { App, Button, Form, Input, Popconfirm, Select, Space, Switch, Tag } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  ModalForm,
  PageContainer,
  ProForm,
  ProFormDigit,
  ProFormSelect,
  ProFormSwitch,
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
  canStoreToggleProductPublication,
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
  archived: '总部强制下线',
};

const PRODUCT_STATUS_OPTIONS = Object.entries(PRODUCT_STATUS_LABELS)
  .filter(([value]) => value !== 'archived')
  .map(([value, label]) => ({ value, label }));

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

  const loadStoreOptions = async (keyword = '') => {
    try {
      const result = await refineDataProvider.getList({
        resource: resources.stores,
        pagination: { currentPage: 1, pageSize: 50, mode: 'server' },
        filters: keyword ? [{ field: 'keyword', operator: 'contains' as const, value: keyword }] : [],
        sorters: [],
      });
      setStores(result.data as Array<{ id: number; name: string; store_code?: string }>);
    } catch {
      message.error('门店列表加载失败，请稍后重试');
    }
  };

  useEffect(() => {
    if (!isHeadquartersAdmin) return;
    void loadStoreOptions();
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
    form.setFieldsValue(product ? productToForm(product) : {
      product_type: 'foot', price: 9.9, member_price_enabled: false, detail_modules: [], display_order: 0, publication_status: 'draft',
    });
    setOpen(true);
  };

  const updatePublication = async (product: Product, publicationStatus: 'published' | 'inactive' | 'archived') => {
    try {
      await refineDataProvider.update({
        resource: resources.products,
        id: product.id,
        variables: { publication_status: publicationStatus },
      });
      message.success(publicationStatus === 'published' ? '商品已上架' : publicationStatus === 'archived' ? '商品已强制下线' : '商品已下架');
      actionRef.current?.reload();
    } catch {
      // 统一错误处理器已提示具体原因，保留当前开关状态由表格刷新恢复。
    }
  };

  const togglePublication = (product: Product, checked: boolean) => updatePublication(product, checked ? 'published' : 'inactive');

  const columns: ProColumns<Product>[] = [
    { title: '商品编码', dataIndex: 'code', width: 140, copyable: true },
    { title: '商品名称', dataIndex: 'name', width: 180, ellipsis: true },
    {
      title: '分类', dataIndex: 'product_type', width: 100, valueType: 'select',
      valueEnum: Object.fromEntries(PRODUCT_TYPE_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => PRODUCT_TYPE_LABELS[record.product_type] || record.product_type,
    },
    {
      title: '价格', dataIndex: 'price_cents', width: 170,
      render: (_, record) => <Space size={4} wrap>
        <Tag>门店 {formatProductPrice(record.price_cents)}</Tag>
        {record.member_price_enabled && record.member_price_cents !== null && record.member_price_cents !== undefined
          ? <Tag color="green">会员 {formatProductPrice(record.member_price_cents)}</Tag>
          : null}
      </Space>,
    },
    { title: '规格', dataIndex: 'spec', width: 140, ellipsis: true },
    { title: '排序', dataIndex: 'display_order', width: 70 },
    {
      title: '状态', dataIndex: 'publication_status', width: 90, valueType: 'select',
      valueEnum: Object.fromEntries(Object.entries(PRODUCT_STATUS_LABELS).map(([value, text]) => [value, { text }])),
      render: (_, record) => <Tag color={record.publication_status === 'published' ? 'green' : record.publication_status === 'inactive' ? 'red' : 'default'}>{PRODUCT_STATUS_LABELS[record.publication_status] || record.publication_status}</Tag>,
    },
    ...(isHeadquartersAdmin ? [{ title: '门店', dataIndex: 'store_id', width: 110 }] : []),
    {
      title: '操作', valueType: 'option', width: isHeadquartersAdmin ? 190 : 160, fixed: 'right',
      render: (_, record) => isHeadquartersAdmin
        ? <Space size={4}>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditor(record)}>编辑</Button>
          {record.publication_status !== 'archived' && <Popconfirm title="确定强制下线该商品吗？店长不能自行恢复。" onConfirm={() => updatePublication(record, 'archived')}><Button size="small" type="link" danger>强制下线</Button></Popconfirm>}
        </Space>
        : <Space size={8}><span>{record.publication_status === 'published' ? '已上架' : '未上架'}</span><Switch size="small" disabled={record.publication_status === 'archived' || !canStoreToggleProductPublication(record.publication_status)} checked={record.publication_status === 'published'} checkedChildren="上架" unCheckedChildren="下架" onChange={(checked) => togglePublication(record, checked)} /></Space>,
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
          return { success: true, data: normalized.data.map((item) => ({ ...item, store_id: item.store_id || storeId || 0 })), total: normalized.total };
        }}
        options={{ density: true, fullScreen: true, reload: true, setting: true }}
        scroll={{ x: 1010 }}
      />
      <ModalForm
        key={editing?.id || 'new-product'}
        form={form}
        title={editing ? '编辑商品' : '新建商品'}
        open={open}
        width={780}
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
        {!editing && <ProFormSelect name="store_id" label="目标门店" options={stores.map((store) => ({ value: store.id, label: `${store.name}${store.store_code ? `（${store.store_code}）` : ''}` }))} fieldProps={{ showSearch: true, filterOption: false, onSearch: (keyword: string) => { void loadStoreOptions(keyword); } }} rules={[{ required: true, message: '请选择目标门店' }]} />}
        <ProFormSelect name="product_type" label="分类" options={PRODUCT_TYPE_OPTIONS} />
        <ProFormDigit name="price" label="价格（元）" min={0} fieldProps={{ precision: 2, addonBefore: '¥' }} rules={[{ required: true, message: '请输入商品价格' }]} />
        <ProFormSwitch name="member_price_enabled" label="启用会员价" />
        <Form.Item noStyle shouldUpdate={(prev, current) => prev.member_price_enabled !== current.member_price_enabled}>
          {({ getFieldValue }) => getFieldValue('member_price_enabled')
            ? <ProFormDigit name="member_price" label="会员价（元）" min={0} fieldProps={{ precision: 2, addonBefore: '¥' }} rules={[{ required: true, message: '启用会员价后请输入价格' }]} />
            : null}
        </Form.Item>
        <ProFormText name="spec" label="规格" />
        <ProFormText name="desc" label="说明" />
        <ProForm.Item name="image_url" label="商品图片"><MediaUploadField purpose="product" /></ProForm.Item>
        <ProFormDigit name="display_order" label="展示顺序" min={0} fieldProps={{ precision: 0 }} />
        {isHeadquartersAdmin && <ProFormSelect name="publication_status" label="目录状态" options={PRODUCT_STATUS_OPTIONS} />}
        <div className="admin-subtitle">商品详情模块</div>
        <Form.List name="detail_modules">
          {(fields, { add, remove }) => <>
            {fields.map(({ key, name, ...restField }) => <div key={key} style={{ marginBottom: 8 }}>
              <Space align="start" style={{ display: 'flex', width: '100%' }}>
                <Form.Item {...restField} name={[name, 'type']} initialValue="text"><Select style={{ width: 100 }} options={[{ value: 'text', label: '文字' }, { value: 'image', label: '图片' }, { value: 'highlight', label: '亮点' }]} /></Form.Item>
                <Form.Item {...restField} name={[name, 'title']}><Input placeholder="标题" /></Form.Item>
                <Form.Item noStyle shouldUpdate={(prev, current) => prev.detail_modules?.[name]?.type !== current.detail_modules?.[name]?.type}>
                  {({ getFieldValue }) => getFieldValue(['detail_modules', name, 'type']) === 'image'
                    ? <Form.Item {...restField} name={[name, 'body']}><MediaUploadField purpose="product_detail" /></Form.Item>
                    : <Form.Item {...restField} name={[name, 'body']}><Input placeholder="内容" /></Form.Item>}
                </Form.Item>
                <Button danger type="text" onClick={() => remove(name)}>删除</Button>
              </Space>
            </div>)}
            <Button type="dashed" onClick={() => add({ type: 'text' })} block>增加详情模块</Button>
          </>}
        </Form.List>
      </ModalForm>
    </PageContainer>
  );
}
