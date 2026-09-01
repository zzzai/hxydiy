import { useEffect, useState } from 'react';
import { App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { copyOptionGroups, createOptionChoice, createOptionGroup, deleteOptionChoice, deleteOptionGroup, getOptionGroups, updateOptionChoice, updateOptionGroup } from '../../api';
import { optionChoiceFormValues, optionChoicePayload, optionGroupPayload, type OptionChoiceForm, type OptionGroupForm } from '../../catalogOptions';

type Props = { projectId: number; projects?: any[] };
type Choice = OptionChoiceForm & { id: number };
type Group = OptionGroupForm & { id: number; choices: Choice[] };

const EMPTY_GROUP: OptionGroupForm = { code: '', name: '', description: '', selection_mode: 'single', required: false, min_select: 0, max_select: 1, display_order: 0 };
const EMPTY_CHOICE: OptionChoiceForm = { code: '', name: '', description: '', choice_type: 'preference', charge_mode: 'free', linked_project_id: null, prices: [], display_order: 0, status: 'active' };

export default function OptionGroupEditor({ projectId, projects = [] }: Props) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [version, setVersion] = useState<any>(null);
  const [groupOpen, setGroupOpen] = useState(false);
  const [choiceOpen, setChoiceOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<Group | null>(null);
  const [editingChoice, setEditingChoice] = useState<{ group: Group; choice: Choice | null } | null>(null);
  const [copySourceId, setCopySourceId] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [groupForm] = Form.useForm<OptionGroupForm>();
  const [choiceForm] = Form.useForm<OptionChoiceForm>();
  const { message } = App.useApp();

  const load = async () => {
    try {
      const response = await getOptionGroups(projectId);
      setGroups(response.data?.items || []);
      setVersion(response.data?.catalog_version || null);
    } catch {
      setGroups([]);
      setVersion(null);
    }
  };
  useEffect(() => { void load(); }, [projectId]);

  const saveGroup = async (values: OptionGroupForm) => {
    setBusy(true);
    try {
      const payload = optionGroupPayload(values);
      if (editingGroup) await updateOptionGroup(projectId, editingGroup.id, payload);
      else await createOptionGroup(projectId, payload);
      setGroupOpen(false); setEditingGroup(null); await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '选项组保存失败');
    } finally { setBusy(false); }
  };

  const saveChoice = async (values: OptionChoiceForm) => {
    if (!editingChoice) return;
    setBusy(true);
    try {
      const payload = optionChoicePayload(values);
      if (editingChoice.choice) await updateOptionChoice(projectId, editingChoice.group.id, editingChoice.choice.id, payload);
      else await createOptionChoice(projectId, editingChoice.group.id, payload);
      setChoiceOpen(false); setEditingChoice(null); await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '选择项保存失败');
    } finally { setBusy(false); }
  };

  const openGroup = (group?: Group) => {
    setEditingGroup(group || null); groupForm.setFieldsValue(group || EMPTY_GROUP); setGroupOpen(true);
  };
  const openChoice = (group: Group, choice?: Choice) => {
    setEditingChoice({ group, choice: choice || null }); choiceForm.setFieldsValue(optionChoiceFormValues(choice || EMPTY_CHOICE)); setChoiceOpen(true);
  };
  const copyFrom = async () => {
    if (!copySourceId) return;
    setBusy(true);
    try {
      await copyOptionGroups(projectId, copySourceId);
      setCopySourceId(undefined);
      await load();
      message.success('已复制到当前目录草稿');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '目录复制失败');
    } finally { setBusy(false); }
  };

  return <div className="catalog-editor">
    <Space style={{ marginBottom: 12 }}>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => openGroup()}>新增选项组</Button>
      <Select allowClear placeholder="从同门店项目复制" style={{ minWidth: 190 }} value={copySourceId} onChange={setCopySourceId} options={projects.filter((project) => project.id !== projectId).map((project) => ({ value: project.id, label: project.name }))} />
      <Button disabled={!copySourceId || version?.status === 'draft'} loading={busy} onClick={copyFrom}>复制目录到草稿</Button>
      {version?.status === 'published' && <Tag color="blue">已发布版本只读，首次保存将创建草稿</Tag>}
      {version?.status === 'draft' && <Tag color="orange">编辑草稿 v{version.version}</Tag>}
    </Space>
    {groups.map((group) => <Card key={group.id} size="small" title={<Space><strong>{group.name}</strong><Tag>{group.selection_mode === 'single' ? '单选' : '多选'}</Tag>{group.required && <Tag color="red">必选</Tag>}<span>{group.min_select}-{group.max_select}</span></Space>} extra={<Space><Button size="small" onClick={() => openGroup(group)}>编辑组</Button><Popconfirm title="删除此选项组？" onConfirm={async () => { setBusy(true); try { await deleteOptionGroup(projectId, group.id); await load(); } catch (error) { message.error(error instanceof Error ? error.message : '选项组删除失败'); } finally { setBusy(false); } }}><Button size="small" danger loading={busy}>删除</Button></Popconfirm></Space>} style={{ marginBottom: 12 }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {group.choices.map((choice) => <Space key={choice.id} style={{ width: '100%', justifyContent: 'space-between' }}>
          <span><strong>{choice.name}</strong> <Tag>{choice.choice_type}</Tag> <small>{choice.charge_mode === 'free' ? '免费' : choice.linked_project_id ? `引用项目 #${choice.linked_project_id}` : '专属收费'}</small></span>
          <Space><Button size="small" onClick={() => openChoice(group, choice)}>编辑</Button><Popconfirm title="删除此选择？" onConfirm={async () => { setBusy(true); try { await deleteOptionChoice(projectId, group.id, choice.id); await load(); } catch (error) { message.error(error instanceof Error ? error.message : '选择项删除失败'); } finally { setBusy(false); } }}><Button size="small" danger loading={busy}>删除</Button></Popconfirm></Space>
        </Space>)}
        <Button type="dashed" block onClick={() => openChoice(group)}>新增选择</Button>
      </Space>
    </Card>)}
    {!groups.length && <Card size="small">还没有目录选项组，请先新增一组。</Card>}
    <Modal open={groupOpen} title={editingGroup ? '编辑选项组' : '新增选项组'} onCancel={() => setGroupOpen(false)} onOk={() => groupForm.submit()} confirmLoading={busy} destroyOnClose>
      <Form form={groupForm} layout="vertical" onFinish={saveGroup} initialValues={EMPTY_GROUP}>
        <Form.Item name="code" label="编码" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="description" label="说明"><Input /></Form.Item>
        <Space><Form.Item name="selection_mode" label="选择方式"><Select options={[{ value: 'single', label: '单选' }, { value: 'multiple', label: '多选' }]} /></Form.Item>
          <Form.Item name="required" label="必选"><Select options={[{ value: false, label: '否' }, { value: true, label: '是' }]} /></Form.Item></Space>
        <Space><Form.Item name="min_select" label="最少"><InputNumber min={0} /></Form.Item><Form.Item name="max_select" label="最多"><InputNumber min={0} /></Form.Item><Form.Item name="display_order" label="排序"><InputNumber min={0} /></Form.Item></Space>
      </Form>
    </Modal>
    <Modal open={choiceOpen} title={editingChoice?.choice ? '编辑选择项' : '新增选择项'} onCancel={() => setChoiceOpen(false)} onOk={() => choiceForm.submit()} confirmLoading={busy} destroyOnClose width={620}>
      <Form form={choiceForm} layout="vertical" onFinish={saveChoice} initialValues={EMPTY_CHOICE}>
        <Space><Form.Item name="code" label="编码" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Space>
        <Form.Item name="description" label="说明"><Input /></Form.Item>
        <Space><Form.Item name="choice_type" label="类型"><Select options={[{ value: 'preference', label: '免费偏好' }, { value: 'linked_project', label: '项目引用' }, { value: 'dedicated_charge', label: '专属收费' }]} /></Form.Item><Form.Item name="status" label="状态"><Select options={[{ value: 'active', label: '启用' }, { value: 'inactive', label: '停用' }]} /></Form.Item></Space>
        <Form.Item noStyle shouldUpdate={(prev, current) => prev.choice_type !== current.choice_type}>{({ getFieldValue }) => getFieldValue('choice_type') === 'linked_project' ? <Form.Item name="linked_project_id" label="引用项目" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={projects.map((project) => ({ value: project.id, label: `${project.name} · 门店/团购/会员 ${JSON.stringify(project.prices || {})}` }))} /></Form.Item> : null}</Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, current) => prev.choice_type !== current.choice_type}>{({ getFieldValue }) => getFieldValue('choice_type') === 'dedicated_charge' ? <Space><Form.Item name={['prices', 0, 'price_type']} initialValue="store"><Input disabled value="store" /></Form.Item><Form.Item name={['prices', 0, 'amount_cents']} label="门店价(分)"><InputNumber min={0} /></Form.Item><Form.Item name={['prices', 1, 'price_type']} initialValue="group"><Input disabled value="group" /></Form.Item><Form.Item name={['prices', 1, 'amount_cents']} label="团购价(分)"><InputNumber min={0} /></Form.Item><Form.Item name={['prices', 2, 'price_type']} initialValue="member"><Input disabled value="member" /></Form.Item><Form.Item name={['prices', 2, 'amount_cents']} label="会员价(分)"><InputNumber min={0} /></Form.Item></Space> : null}</Form.Item>
        <Space><Form.Item name="independently_visible" label="独立展示"><Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} /></Form.Item><Form.Item name="qualifies_for_foot_bath_bundle" label="计入泡脚减免"><Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} /></Form.Item><Form.Item name="display_order" label="排序"><InputNumber min={0} /></Form.Item></Space>
      </Form>
    </Modal>
  </div>;
}
