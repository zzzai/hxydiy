import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Skeleton, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { ensureCatalogDraft, copyOptionGroups, createOptionChoice, createOptionGroup, deleteOptionChoice, deleteOptionGroup, getOptionGroups, getProjectsAdmin, updateOptionChoice, updateOptionGroup } from '../../api';
import { CHOICE_TYPE_LABELS, linkedProjectLabel, yuanToCents, optionChoiceFormValues, optionChoicePayload, optionGroupPayload, type OptionChoiceForm, type OptionGroupForm } from '../../catalogOptions';

import { requestErrorMessage } from '../../requestError';

type Props = { projectId: number; storeId: number };
type Choice = OptionChoiceForm & { id: number };
type Group = OptionGroupForm & { id: number; choices: Choice[] };

const EMPTY_GROUP: OptionGroupForm = { code: '', name: '', description: '', selection_mode: 'single', required: false, min_select: 0, max_select: 1, display_order: 0 };
const EMPTY_CHOICE: OptionChoiceForm = { code: '', name: '', description: '', choice_type: 'preference', charge_mode: 'free', linked_project_id: null, prices: [], display_order: 0, status: 'active' };

export default function OptionGroupEditor({ projectId, storeId }: Props) {
  const [projects, setProjects] = useState<any[]>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const requestId = useRef(0);
  const [groups, setGroups] = useState<Group[]>([]);
  const [version, setVersion] = useState<any>(null);
  const [groupOpen, setGroupOpen] = useState(false);
  const [choiceOpen, setChoiceOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<Group | null>(null);
  const [editingChoice, setEditingChoice] = useState<{ group: Group; choice: Choice | null } | null>(null);
  const [copySourceId, setCopySourceId] = useState<number>();
  const [busy, setBusy] = useState(false);
  const writing = useRef(false);
  const [writeError, setWriteError] = useState('');
  const editable = !version || version.status === 'draft';
  const [groupForm] = Form.useForm<OptionGroupForm>();
  const [choiceForm] = Form.useForm<OptionChoiceForm>();
  const { message, modal } = App.useApp();
  const [editDirty, setEditDirty] = useState(false);
  const closeNested = (kind: 'group' | 'choice') => {
    if (busy) return;
    const close = () => { setEditDirty(false); kind === 'group' ? setGroupOpen(false) : setChoiceOpen(false); };
    if (!editDirty) { close(); return; }
    modal.confirm({ title: '可选内容还没有保存', content: '关闭会丢弃本次未保存的修改。', okText: '放弃修改', cancelText: '继续编辑', onOk: close });
  };

  const load = async () => {
    const request = ++requestId.current;
    setLoadState('loading');
    try {
      if (!storeId) throw new Error('Missing store scope');
      const [response, candidates] = await Promise.all([getOptionGroups(projectId), getProjectsAdmin(storeId)]);
      if (request !== requestId.current) return;
      if (!Array.isArray(candidates.data) || !Array.isArray(response.data?.items)) throw new Error('Incomplete catalog response');
      setProjects(candidates.data.filter((project: any) => project.store_id === storeId && project.id !== projectId));
      setGroups(response.data?.items || []);
      setVersion(response.data?.catalog_version || null);
      setLoadState('ready');
    } catch {
      if (request === requestId.current) setLoadState('error');
    }
  };
  useEffect(() => { void load(); return () => { requestId.current++; }; }, [projectId, storeId]);

  const saveGroup = async (values: OptionGroupForm) => {
    if (writing.current || !editable) return;
    writing.current = true; setBusy(true); setWriteError('');
    try {
      const payload = optionGroupPayload(values);
      if (editingGroup) await updateOptionGroup(projectId, editingGroup.id, payload);
      else await createOptionGroup(projectId, payload);
      setGroupOpen(false); setEditingGroup(null); await load();
    } catch (error) {
      setWriteError(requestErrorMessage(error));
    } finally { writing.current = false; setBusy(false); }
  };

  const saveChoice = async (values: OptionChoiceForm) => {
    if (!editingChoice || writing.current || !editable) return;
    writing.current = true; setBusy(true); setWriteError('');
    try {
      const payload = optionChoicePayload(values);
      if (editingChoice.choice) await updateOptionChoice(projectId, editingChoice.group.id, editingChoice.choice.id, payload);
      else await createOptionChoice(projectId, editingChoice.group.id, payload);
      setChoiceOpen(false); setEditingChoice(null); await load();
    } catch (error) {
      setWriteError(requestErrorMessage(error));
    } finally { writing.current = false; setBusy(false); }
  };

  const openGroup = (group?: Group) => {
    if (!editable || busy) return;
    setWriteError(''); setEditDirty(false); groupForm.resetFields(); setEditingGroup(group || null); groupForm.setFieldsValue(group || EMPTY_GROUP); setGroupOpen(true);
  };
  const openChoice = (group: Group, choice?: Choice) => {
    if (!editable || busy) return;
    setWriteError(''); setEditDirty(false); choiceForm.resetFields(); setEditingChoice({ group, choice: choice || null }); choiceForm.setFieldsValue(optionChoiceFormValues(choice || EMPTY_CHOICE)); setChoiceOpen(true);
  };
  const beginDraft = async () => {
    if (writing.current) return;
    writing.current = true; setBusy(true); setWriteError('');
    try {
      await ensureCatalogDraft(projectId);
      await load();
    } catch (error) { setWriteError(requestErrorMessage(error)); }
    finally { writing.current = false; setBusy(false); }
  };
  const copyFrom = async () => {
    if (!copySourceId || writing.current) return;
    writing.current = true; setBusy(true); setWriteError('');
    try {
      await copyOptionGroups(projectId, copySourceId);
      setCopySourceId(undefined);
      await load();
      message.success('已复制到当前目录草稿');
    } catch (error) {
      setWriteError(requestErrorMessage(error));
    } finally { writing.current = false; setBusy(false); }
  };

  if (loadState === 'loading') return <div className="catalog-editor-state" role="status"><p>正在加载可选内容…</p><Skeleton active /></div>;
  if (loadState === 'error') return <Alert className="catalog-editor-state" type="error" showIcon message="可选内容加载失败" description="请重新加载，确认当前可选内容后再编辑。" action={<Button onClick={() => void load()}>重新加载</Button>} />;

  return <div className="catalog-editor">
    <Alert type="info" showIcon message={version?.status === 'published' ? '当前展示已发布内容。创建编辑草稿后修改，发布前顾客仍看到原版本。' : '可选内容单独保存到草稿；完成后到“检查与发布”生效。'} action={version?.status === 'published' ? <Button type="primary" loading={busy} onClick={beginDraft}>创建编辑草稿</Button> : undefined} />
    {writeError && !groupOpen && !choiceOpen && <Alert type="error" showIcon message={writeError} description="请重新加载核对操作结果；现有目录不会被清空。" action={<Button onClick={() => void load()}>重新加载</Button>} />}
    <div className="catalog-editor-toolbar">
      <Button type="primary" icon={<PlusOutlined />} disabled={!editable || busy} onClick={() => openGroup()}>新增选项组</Button>
      <Select allowClear placeholder="从同门店项目复制" style={{ minWidth: 190 }} value={copySourceId} onChange={setCopySourceId} options={projects.filter((project) => project.id !== projectId).map((project) => ({ value: project.id, label: project.name }))} />
      <Button disabled={!copySourceId || version?.status === 'draft'} loading={busy} onClick={copyFrom}>复制目录到草稿</Button>
      {version?.status === 'published' && <Tag color="blue">已发布 · 只读</Tag>}
      {version?.status === 'draft' && <Tag color="orange">编辑草稿 v{version.version}</Tag>}
    </div>
    {groups.map((group) => <Card key={group.id} size="small" title={<Space><strong>{group.name}</strong><Tag>{group.selection_mode === 'single' ? '单选' : '多选'}</Tag>{group.required && <Tag color="red">必选</Tag>}<span>{group.min_select}-{group.max_select}</span></Space>} extra={<Space><Button size="small" disabled={!editable || busy} onClick={() => openGroup(group)}>编辑组</Button><Popconfirm title="删除此选项组？" onConfirm={async () => { setBusy(true); try { await deleteOptionGroup(projectId, group.id); await load(); } catch (error) { setWriteError(requestErrorMessage(error)); } finally { setBusy(false); } }}><Button size="small" danger disabled={!editable} loading={busy}>删除</Button></Popconfirm></Space>} style={{ marginBottom: 12 }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {group.choices.map((choice) => <div key={choice.id} className="catalog-choice-row">
          <span><strong>{choice.name}</strong> <Tag>{CHOICE_TYPE_LABELS[choice.choice_type || ''] || '待核对类型'}</Tag> <small>{choice.charge_mode === 'free' ? '不加价' : choice.linked_project_id ? (() => { const project = projects.find((item) => item.id === choice.linked_project_id); return project ? linkedProjectLabel(project) : '关联项目不可用，请检查门店和上架状态'; })() : '按已配置价格收费'}</small></span>
          <Space><Button size="small" disabled={!editable || busy} onClick={() => openChoice(group, choice)}>编辑</Button><Popconfirm title="删除此选择？" onConfirm={async () => { setBusy(true); try { await deleteOptionChoice(projectId, group.id, choice.id); await load(); } catch (error) { setWriteError(requestErrorMessage(error)); } finally { setBusy(false); } }}><Button size="small" danger disabled={!editable} loading={busy}>删除</Button></Popconfirm></Space>
        </div>)}
        <Button type="dashed" block disabled={!editable || busy} onClick={() => openChoice(group)}>新增选择</Button>
      </Space>
    </Card>)}
    {!groups.length && <Card size="small">还没有目录选项组，请先新增一组。</Card>}
    <Modal open={groupOpen} title={editingGroup ? '编辑选项组' : '新增选项组'} onCancel={() => closeNested('group')} onOk={() => groupForm.submit()} confirmLoading={busy} destroyOnClose maskClosable={false} okText="保存到草稿" cancelText="关闭" className="project-option-modal" style={{ top: 24 }}>
      <>{writeError && <Alert type="error" showIcon message={writeError} description="填写内容已保留。若状态已变化，请关闭后重新加载目录，再核对修改。" />}<Form name="project-option-group" form={groupForm} layout="vertical" className="project-option-form" onValuesChange={() => setEditDirty(true)} onFinish={saveGroup} initialValues={EMPTY_GROUP}>
        <Form.Item name="code" label="编码" rules={[{ required: true, whitespace: true }, { max: 32, message: '最多 32 个字符' }]}><Input maxLength={32} /></Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }, { max: 64, message: '最多 64 个字符' }]}><Input maxLength={64} /></Form.Item>
        <Form.Item name="description" label="说明" rules={[{ max: 512, message: '说明最多 512 个字' }]}><Input maxLength={512} /></Form.Item>
        <Space><Form.Item name="selection_mode" label="选择方式"><Select options={[{ value: 'single', label: '单选' }, { value: 'multiple', label: '多选' }]} /></Form.Item>
          <Form.Item name="required" label="必选"><Select options={[{ value: false, label: '否' }, { value: true, label: '是' }]} /></Form.Item></Space>
        <Space><Form.Item name="min_select" label="最少"><InputNumber min={0} /></Form.Item><Form.Item name="max_select" label="最多"><InputNumber min={0} /></Form.Item><Form.Item name="display_order" label="排序"><InputNumber min={0} /></Form.Item></Space>
      </Form></>
    </Modal>
    <Modal open={choiceOpen} title={editingChoice?.choice ? '编辑选择项' : '新增选择项'} onCancel={() => closeNested('choice')} onOk={() => choiceForm.submit()} confirmLoading={busy} destroyOnClose width={620} maskClosable={false} okText="保存到草稿" cancelText="关闭" className="project-option-modal" style={{ top: 24 }}>
      <>{writeError && <Alert type="error" showIcon message={writeError} description="填写内容已保留。若状态已变化，请关闭后重新加载目录，再核对修改。" />}<Form name="project-option-choice" form={choiceForm} layout="vertical" className="project-option-form" onValuesChange={() => setEditDirty(true)} onFinish={saveChoice} initialValues={EMPTY_CHOICE}>
        <Space><Form.Item name="code" label="编码" rules={[{ required: true, whitespace: true }, { max: 32, message: '最多 32 个字符' }]}><Input maxLength={32} /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true }, { max: 64, message: '最多 64 个字符' }]}><Input maxLength={64} /></Form.Item></Space>
        <Form.Item name="description" label="说明" rules={[{ max: 512, message: '说明最多 512 个字' }]}><Input maxLength={512} /></Form.Item>
        <Space><Form.Item name="choice_type" label="类型"><Select options={[{ value: 'preference', label: '免费偏好' }, { value: 'linked_project', label: '项目引用' }, { value: 'dedicated_charge', label: '专属收费' }]} /></Form.Item><Form.Item name="status" label="状态"><Select options={[{ value: 'active', label: '启用' }, { value: 'inactive', label: '停用' }]} /></Form.Item></Space>
        <Form.Item noStyle shouldUpdate={(prev, current) => prev.choice_type !== current.choice_type}>{({ getFieldValue }) => getFieldValue('choice_type') === 'linked_project' ? <Form.Item name="linked_project_id" label="关联服务项目" rules={[{ required: true, message: '请选择关联项目' }]}><Select showSearch optionFilterProp="label" options={projects.map((project) => ({ value: project.id, label: linkedProjectLabel(project) }))} /></Form.Item> : null}</Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, current) => prev.choice_type !== current.choice_type}>{({ getFieldValue }) => getFieldValue('choice_type') === 'dedicated_charge' ? <div className="project-price-grid">{(['store', 'group', 'member'] as const).map((type, index) => <div key={type}><Form.Item name={['prices', index, 'price_type']} initialValue={type} hidden><Input /></Form.Item><Form.Item name={['prices', index, 'amount_cents']} label={`${{ store: '门店', group: '团购', member: '会员' }[type]}价（元）`} getValueProps={(value) => ({ value: typeof value === 'number' ? value / 100 : value })} normalize={yuanToCents} rules={[{ required: true, message: '请填写金额，免费请填 0' }]}><InputNumber min={0} precision={2} style={{ width: '100%' }} /></Form.Item></div>)}</div> : null}</Form.Item>
        <Space><Form.Item name="independently_visible" label="独立展示"><Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} /></Form.Item><Form.Item name="qualifies_for_foot_bath_bundle" label="计入泡脚减免"><Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} /></Form.Item><Form.Item name="display_order" label="排序"><InputNumber min={0} /></Form.Item></Space>
      </Form></>
    </Modal>
  </div>;
}
