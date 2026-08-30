import { useState } from 'react';
import { App, Button, Form, Space, Tabs, Tag } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  ModalForm,
  PageContainer,
  ProTable,
  type ActionType,
  type ProColumns,
} from '@ant-design/pro-components';
import { getStaff } from '../api';
import { canManageConfiguration, getStoreId } from '../auth';
import { refineDataProvider } from '../core/dataProvider/refine';
import { resources } from '../core/resources';
import { projectFormPayload, projectToForm } from '../projectContent';
import ProjectBasicFields from '../components/project-options/ProjectBasicFields';
import OptionGroupEditor from '../components/project-options/OptionGroupEditor';
import CatalogPublishPanel from '../components/project-options/CatalogPublishPanel';
import {
  CATEGORY_LABELS,
  CATEGORY_OPTIONS,
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
  if (status === 'inactive' || status === 'archived') return 'default';
  return 'gold';
}

export default function ProjectsPage() {
  const { message } = App.useApp();
  const staff = getStaff();
  const canManage = canManageConfiguration(staff?.role);
  const [actionRef] = useState<React.MutableRefObject<ActionType | undefined>>({ current: undefined });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [form] = Form.useForm();

  if (!canManage) {
    return <PageContainer title="服务项目" content="仅管理员或店长可以管理服务项目。"><div /></PageContainer>;
  }
  if (!staff?.store_id) {
    return <PageContainer title="服务项目" content="当前账号未绑定门店，请切换到具体门店后管理服务项目。"><div /></PageContainer>;
  }

  const openEditor = (project?: Project) => {
    setEditing(project || null);
    form.resetFields();
    if (project) form.setFieldsValue(projectToForm(project));
    setOpen(true);
  };

  const columns: ProColumns<Project>[] = [
    { title: '项目编码', dataIndex: 'code', width: 140, copyable: true },
    {
      title: '项目名称', dataIndex: 'name', width: 190, ellipsis: true,
      render: (_, record) => <Space size={4}><strong>{record.name}</strong>{record.category_mark && <Tag>{record.category_mark}</Tag>}</Space>,
    },
    {
      title: '分类', dataIndex: 'category', width: 110, valueType: 'select',
      valueEnum: Object.fromEntries(CATEGORY_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => CATEGORY_LABELS[record.category] || record.category,
    },
    { title: '时长', dataIndex: 'duration_min', width: 80, render: (_, record) => record.duration_min ? `${record.duration_min}分钟` : '-' },
    {
      title: '价格', dataIndex: 'prices', width: 250,
      render: (_, record) => <Space size={4} wrap>{Object.entries(record.prices || {}).map(([type, cents]) => <Tag key={type} color={type === 'member' ? 'green' : undefined}>{priceLabels[type] || type} {formatProjectPrice(cents)}</Tag>)}</Space>,
    },
    {
      title: '状态', dataIndex: 'publication_status', width: 100, valueType: 'select',
      valueEnum: Object.fromEntries(PROJECT_STATUS_OPTIONS.map((item) => [item.value, { text: item.label }])),
      render: (_, record) => <Tag color={projectStatusColor(record.publication_status)}>{PROJECT_STATUS_LABELS[record.publication_status] || record.publication_status}</Tag>,
    },
    {
      title: '操作', valueType: 'option', width: 100, fixed: 'right',
      render: (_, record) => <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(record)}>编辑内容</Button>,
    },
  ];

  return (
    <PageContainer
      title="服务项目"
      content="维护门店服务项目、价格和顾客可选内容。"
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>刷新</Button>,
        <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>新建项目</Button>,
      ]}
    >
      <ProTable<Project>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        search={{ labelWidth: 'auto', defaultCollapsed: true }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        request={async (params) => {
          const result = await refineDataProvider.getList({
            resource: resources.projects,
            pagination: { currentPage: params.current, pageSize: params.pageSize, mode: 'server' },
            filters: Object.entries(projectFilterParams({
              publication_status: params.publication_status,
              category: params.category,
            })).map(([field, value]) => ({ field, operator: 'eq' as const, value })),
            sorters: [],
          });
          const normalized = normalizeProjectList(result);
          setProjects(normalized.data);
          const filtered = normalized.data.filter((project) =>
            (!params.publication_status || project.publication_status === params.publication_status)
            && (!params.category || project.category === params.category),
          );
          return { success: true, data: filtered, total: filtered.length };
        }}
        options={{ density: true, fullScreen: true, reload: true, setting: true }}
        scroll={{ x: 980 }}
      />
      <ModalForm
        key={editing?.id || 'new-project'}
        form={form}
        title={editing ? '编辑项目内容' : '新建项目'}
        open={open}
        width={780}
        modalProps={{ destroyOnClose: true }}
        onOpenChange={(nextOpen) => {
          setOpen(nextOpen);
          if (!nextOpen) { setEditing(null); form.resetFields(); }
        }}
        onFinish={async (values) => {
          const storeId = getStoreId(getStaff());
          const payload = projectFormPayload(values);
          if (editing) {
            await refineDataProvider.update({ resource: resources.projects, id: editing.id, variables: payload });
            message.success('项目内容已保存');
          } else {
            await refineDataProvider.create({ resource: resources.projects, variables: { ...payload, store_id: storeId, price_label: '' } });
            message.success('项目已创建');
          }
          actionRef.current?.reload();
          setEditing(null);
          return true;
        }}
      >
        <Tabs
          destroyOnHidden
          items={[
            { key: 'basic', label: '基本信息', children: <ProjectBasicFields form={form} editing={editing} /> },
            ...(editing ? [
              { key: 'options', label: '可选项', children: <OptionGroupEditor projectId={editing.id} projects={projects} /> },
              { key: 'publish', label: '发布检查', children: <CatalogPublishPanel projectId={editing.id} /> },
            ] : []),
          ]}
        />
      </ModalForm>
    </PageContainer>
  );
}
