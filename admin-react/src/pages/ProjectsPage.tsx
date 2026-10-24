import { dataProvider } from '../core/dataProvider';
import { requestErrorMessage } from '../requestError';
import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Form, Popconfirm, Space, Switch, Tabs, Tag } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  ModalForm,
  PageContainer,
  ProFormSelect,
  ProTable,
  type ActionType,
  type ProColumns,
} from '@ant-design/pro-components';
import { getStaff } from '../api';
import { canManageConfiguration, canManageStoreMasterData, getStoreId } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import { projectFormPayload, projectToForm } from '../projectContent';
import ProjectBasicFields from '../components/project-options/ProjectBasicFields';
import OptionGroupEditor from '../components/project-options/OptionGroupEditor';
import CatalogPublishPanel from '../components/project-options/CatalogPublishPanel';
import '../components/project-options/project-editor.css';
import {
  CATEGORY_LABELS,
  CATEGORY_OPTIONS,
  canStoreToggleProjectPublication,
  formatProjectPrice,
  normalizeProjectList,
  PROJECT_STATUS_LABELS,
  PROJECT_STATUS_OPTIONS,
  projectFilterParams,
  type Project,
} from './projects-page-model';

const priceLabels: Record<string, string> = { store: '门店', group: '团购', member: '会员' };

function projectStatusColor(status: string) {
  if (status === 'published') return 'green';
  if (status === 'inactive') return 'red';
  if (status === 'archived') return 'default';
  return 'gold';
}

export default function ProjectsPage() {
  const { message, modal } = App.useApp();
  const staff = getStaff();
  const canManage = canManageConfiguration(staff?.role);
  const isHeadquartersAdmin = canManageStoreMasterData(staff?.role, staff?.store_id);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [stores, setStores] = useState<Array<{ id: number; name: string; store_code?: string }>>([]);
  const [form] = Form.useForm();
  const [activeTab, setActiveTab] = useState('basic');
  const [basicDirty, setBasicDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveBusy = useRef(false);
  const [saveError, setSaveError] = useState('');
  const [listError, setListError] = useState('');
  const [storeError, setStoreError] = useState('');
  const refreshProjects = () => { dataProvider.invalidate(resources.projects); actionRef.current?.reload(); };

  const loadStoreOptions = async (keyword = '') => {
    setStoreError('');
    try {
      const result = await refineDataProvider.getList({
        resource: resources.stores,
        pagination: { currentPage: 1, pageSize: 50, mode: 'server' },
        filters: keyword ? [{ field: 'keyword', operator: 'contains' as const, value: keyword }] : [],
        sorters: [],
      });
      setStores(result.data as Array<{ id: number; name: string; store_code?: string }>);
    } catch (error) { setStoreError(requestErrorMessage(error)); }
  };

  useEffect(() => {
    if (!isHeadquartersAdmin) return;
    void loadStoreOptions();
  }, [isHeadquartersAdmin, message]);

  if (!canManage) {
    return <PageContainer title="服务项目" content="仅管理员或店长可以管理服务项目。"><div /></PageContainer>;
  }
  if (!isHeadquartersAdmin && !staff?.store_id) {
    return <PageContainer title="服务项目" content="当前账号未绑定门店，请切换到具体门店后管理服务项目。"><div /></PageContainer>;
  }

  const openEditor = (project?: Project) => {
    if (saveBusy.current) return;
    setActiveTab('basic'); setBasicDirty(false); setSaveError('');
    setEditing(project || null);
    form.resetFields();
    if (project) form.setFieldsValue(projectToForm(project));
    setOpen(true);
  };

  const closeEditor = () => { setOpen(false); setEditing(null); setBasicDirty(false); setSaveError(''); form.resetFields(); };
  const requestClose = () => {
    if (saveBusy.current) return;
    if (!basicDirty) { closeEditor(); return; }
    modal.confirm({
      title: '项目资料还没有保存', content: '关闭会丢弃当前未保存的项目资料。已经保存的可选内容草稿不受影响。',
      okText: '放弃修改并关闭', cancelText: '继续编辑', onOk: closeEditor,
    });
  };

  const updatePublication = async (project: Project, publicationStatus: 'published' | 'inactive' | 'archived') => {
    try {
      await refineDataProvider.update({
        resource: resources.projects,
        id: project.id,
        variables: { publication_status: publicationStatus },
      });
      message.success(publicationStatus === 'published' ? '项目已上架' : publicationStatus === 'archived' ? '项目已强制下线' : '项目已下架');
      actionRef.current?.reload();
    } catch {
      // 统一错误处理器会显示服务端权限或状态错误，并由刷新恢复开关状态。
    }
  };

  const togglePublication = (project: Project, checked: boolean) => updatePublication(project, checked ? 'published' : 'inactive');

  const columns: ProColumns<Project>[] = [
    { title: '项目编码', dataIndex: 'code', hideInTable: true, search: false },
    {
      title: '项目名称', dataIndex: 'name', width: 190, ellipsis: true, search: false,
      render: (_, record) => <Space size={4}><strong>{record.name}</strong>{record.category_mark && <Tag>{record.category_mark}</Tag>}</Space>,
    },
    {
      title: '分类', dataIndex: 'category', width: 110, valueType: 'select',
      valueEnum: Object.fromEntries(CATEGORY_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => CATEGORY_LABELS[record.category] || record.category,
    },
    { title: '时长', dataIndex: 'duration_min', width: 80, search: false, render: (_, record) => record.duration_min ? `${record.duration_min}分钟` : '-' },
    {
      title: '价格', dataIndex: 'prices', width: 250, search: false,
      render: (_, record) => <Space size={4} wrap>{Object.entries(record.prices || {}).map(([type, cents]) => <Tag key={type} color={type === 'member' ? 'green' : undefined}>{priceLabels[type] || type} {formatProjectPrice(cents)}</Tag>)}</Space>,
    },
    {
      title: '状态', dataIndex: 'publication_status', width: 100, valueType: 'select',
      valueEnum: Object.fromEntries(PROJECT_STATUS_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => <Tag color={projectStatusColor(record.publication_status)}>{PROJECT_STATUS_LABELS[record.publication_status] || record.publication_status}</Tag>,
    },
    ...(isHeadquartersAdmin ? [{ title: '门店', dataIndex: 'store_id', width: 150, search: false, render: (_: unknown, record: Project) => stores.find(store => store.id === record.store_id)?.name || `门店 ${record.store_id}` }] : []),
    {
      title: '操作', valueType: 'option', width: isHeadquartersAdmin ? 190 : 160, fixed: 'right',
      render: (_, record) => isHeadquartersAdmin
        ? <Space size={4}>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditor(record)}>编辑内容</Button>
          {record.publication_status !== 'archived' && <Popconfirm title="确定强制下线该项目吗？店长不能恢复。" onConfirm={() => updatePublication(record, 'archived')}><Button size="small" type="link" danger>强制下线</Button></Popconfirm>}
        </Space>
        : <Space size={8}>
          <span>{record.publication_status === 'published' ? '已上架' : '未上架'}</span>
          <Switch
            size="small"
            disabled={record.publication_status === 'archived' || !canStoreToggleProjectPublication(record.publication_status)}
            checked={record.publication_status === 'published'}
            checkedChildren="上架"
            unCheckedChildren="下架"
            onChange={(checked) => togglePublication(record, checked)}
          />
        </Space>,
    },
  ];

  return (
    <PageContainer
      title="服务项目"
      content="维护门店服务项目、价格和顾客可选内容。"
        extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={refreshProjects}>刷新</Button>,
        ...(isHeadquartersAdmin ? [<Button key="create" disabled={!!listError || !!storeError} type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>新建项目</Button>] : []),
      ]}
    >
      {storeError && <Alert type="error" showIcon message="门店列表未能加载" description={storeError} action={<Button onClick={() => { dataProvider.invalidate(resources.stores); void loadStoreOptions(); }}>重试门店列表</Button>} style={{ marginBottom: 16 }} />}
      {listError && <Alert type="error" showIcon message="服务项目列表未能加载" description={listError} action={<Button onClick={refreshProjects}>重新加载项目</Button>} style={{ marginBottom: 16 }} />}
      <ProTable<Project>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        search={{ labelWidth: 'auto', defaultCollapsed: true }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        request={async (params) => {
          setListError('');
          try {
          const result = await refineDataProvider.getList({
            resource: resources.projects,
            pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' },
            filters: Object.entries(projectFilterParams({
              publication_status: params.publication_status,
              category: params.category,
            })).map(([field, value]) => ({ field, operator: 'eq' as const, value })),
            sorters: [],
          });
          const normalized = normalizeProjectList({ data: result.data as Project[], total: result.total });
          setProjects(normalized.data);
          return { success: true, data: normalized.data, total: normalized.total };
          } catch (error) { setListError(requestErrorMessage(error)); return { success: false, data: [], total: 0 }; }
        }}
        options={{ density: true, fullScreen: true, reload: false, setting: true }}
        locale={{ emptyText: listError ? '读取失败，请使用上方“重新加载项目”重试' : '当前条件下没有服务项目' }}
        scroll={{ x: 980 }}
      />
      <ModalForm
        name="project-editor"
        key={editing?.id || 'new-project'}
        form={form}
        title={editing ? `编辑项目 · ${editing.name}` : '新建服务项目'}
        open={open}
        width={1100}
        modalProps={{ destroyOnClose: true, maskClosable: false, className: 'project-editor-modal', style: { top: 24 } }}
        onValuesChange={() => { setBasicDirty(true); setSaveError(''); }}
        submitter={{ render: (props) => <Space><Button disabled={saving} onClick={requestClose}>关闭</Button>{activeTab === 'basic' && <Button type="primary" loading={saving} onClick={() => props.form?.submit()}>保存项目资料</Button>}</Space> }}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) requestClose();
          else setOpen(true);
        }}
        onFinish={async (values) => {
          if (saveBusy.current) return false;
          saveBusy.current = true; setSaving(true);
          setSaveError('');
          try {
          const payload = projectFormPayload(values);
          if (editing) {
            await refineDataProvider.update({ resource: resources.projects, id: editing.id, variables: payload });
            message.success('项目内容已保存');
          } else {
            const storeId = isHeadquartersAdmin ? Number(values.store_id) : getStoreId(getStaff());
            await refineDataProvider.create({ resource: resources.projects, variables: { ...payload, store_id: storeId, price_label: '' } });
            message.success('项目已创建');
          }
          actionRef.current?.reload();
          closeEditor();
          return false;
          } catch (error) {
            setSaveError(requestErrorMessage(error));
            return false;
          } finally { saveBusy.current = false; setSaving(false); }
        }}
      >
        {saveError && <Alert type="error" showIcon message="项目资料保存失败" description={`填写内容已保留。${saveError}`} style={{ marginBottom: 16 }} />}
        {basicDirty && activeTab !== 'basic' && <Alert type="warning" showIcon message="项目资料有未保存的修改" description="请先回到“项目资料”保存，再检查并发布可选内容。" style={{ marginBottom: 16 }} />}
        {!editing && isHeadquartersAdmin && <ProFormSelect name="store_id" label="目标门店" options={stores.map((store) => ({ value: store.id, label: `${store.name}${store.store_code ? `（${store.store_code}）` : ''}` }))} fieldProps={{ showSearch: true, filterOption: false, onSearch: (keyword: string) => { void loadStoreOptions(keyword); } }} rules={[{ required: true, message: '请选择目标门店' }]} />}
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { key: 'basic', label: '项目资料', forceRender: true, children: <><p className="project-save-note">保存会更新项目资料；可选内容的草稿在“检查与发布”中单独生效。</p><ProjectBasicFields form={form} editing={editing} onDirty={() => setBasicDirty(true)} /></> },
            ...(editing ? [
              { key: 'options', label: '顾客可选内容', children: activeTab === 'options' ? <OptionGroupEditor projectId={editing.id} storeId={editing.store_id} /> : null },
              { key: 'publish', label: '检查与发布', children: activeTab === 'publish' ? <CatalogPublishPanel projectId={editing.id} blocked={basicDirty} /> : null },
            ] : []),
          ]}
        />
      </ModalForm>
    </PageContainer>
  );
}
