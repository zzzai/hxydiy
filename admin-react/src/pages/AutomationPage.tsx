import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, InputNumber, Modal, Select, Space, Table, Tag } from 'antd';
import { getAutomations, createAutomation, getAutomationLogs, getTags } from '../api';
import { getStaff } from '../api';
import StoreScopeSelect from '../components/StoreScopeSelect';
import { requestErrorMessage } from '../requestError';
import { ACTION_LABELS, TRIGGER_LABELS, automationActionText, disabledTagRule } from '../businessDisplay';

export default function AutomationPage() {
  const { message, modal } = App.useApp(); const staff = getStaff();
  const [storeId, setStoreId] = useState<number | undefined>(staff?.store_id || undefined);
  const [data, setData] = useState<any[]>([]), [tags, setTags] = useState<any[]>([]);
  const [loading, setLoading] = useState(false), [error, setError] = useState(''), [open, setOpen] = useState(false), [dirty, setDirty] = useState(false), [saving, setSaving] = useState(false), [saveError, setSaveError] = useState('');
  const [logRule, setLogRule] = useState<any>(), [logs, setLogs] = useState<any[]>([]), [logLoading, setLogLoading] = useState(false), [logError, setLogError] = useState(''), [logPage, setLogPage] = useState(1), [logTotal, setLogTotal] = useState(0);
  const sequence = useRef(0), logSequence = useRef(0), busy = useRef(false); const [form] = Form.useForm();
  const canConfigure = !!staff?.store_id && staff.store_id === storeId && ['manager', 'admin'].includes(staff.role || '');
  const load = async () => { if (!storeId) return; const request = ++sequence.current; setLoading(true); setError(''); try { const rows = await getAutomations(storeId); const tagRows = canConfigure ? await getTags() : undefined; if (request !== sequence.current) return; setData(rows.data || []); setTags(tagRows?.data || []); } catch (err) { if (request === sequence.current) setError(requestErrorMessage(err)); } finally { if (request === sequence.current) setLoading(false); } };
  useEffect(() => { setData([]); setLogRule(undefined); setLogs([]); logSequence.current++; void load(); return () => { sequence.current++; logSequence.current++; }; }, [storeId]);
  const loadLogs = async (rule: any, page = 1) => { const request = ++logSequence.current; setLogRule(rule); setLogLoading(true); setLogError(''); setLogs([]); try { const response = await getAutomationLogs(rule.id, storeId, page, 20); if (request !== logSequence.current) return; setLogs(response.data.items || []); setLogTotal(response.data.total || 0); setLogPage(page); } catch (err) { if (request === logSequence.current) setLogError(requestErrorMessage(err)); } finally { if (request === logSequence.current) setLogLoading(false); } };
  const close = () => { if (saving) return; if (dirty) modal.confirm({ title: '规则还未保存', okText: '放弃填写', cancelText: '继续编辑', onOk: () => { setOpen(false); setDirty(false); } }); else setOpen(false); };
  return <div><div className="page-heading"><div><h2>自动化规则</h2><div className="page-kicker">核对规则配置与已有执行记录</div></div><Space wrap><StoreScopeSelect value={storeId} onChange={setStoreId} disabled={open || saving} /><Button onClick={() => void load()} loading={loading} disabled={!storeId}>刷新</Button>{canConfigure && <Button type="primary" disabled={loading || !!error} onClick={() => { form.resetFields(); setDirty(false); setSaveError(''); setOpen(true); }}>新建停用规则</Button>}</Space></div>
    <Alert type="info" showIcon message="当前只维护配置，未接通规则执行" description="本页不启用规则、不发券、不发送消息。已有启用标记照实保留，不代表规则正在运行；新规则只保存为停用。" style={{ marginBottom: 16 }} />
    {!storeId ? <Empty description="请选择要查看的门店" /> : <>{error && <Alert type="error" message="规则读取失败" description={error} action={<Button onClick={() => void load()}>重试</Button>} style={{ marginBottom: 16 }} />}<Card><Table rowKey="id" loading={loading} dataSource={data} pagination={false} scroll={{ x: 760 }} locale={{ emptyText: error ? '读取未完成，请重试' : '本店暂无规则配置' }} columns={[
      { title: '规则', dataIndex: 'name', render: (value: string, row: any) => <><strong>{value}</strong><div style={{ color: '#536158' }}>{row.description}</div></> },
      { title: '触发条件', dataIndex: 'trigger_event', render: (value: string) => TRIGGER_LABELS[value] || '旧版条件待核验' },
      { title: '计划动作', dataIndex: 'actions', render: (value: unknown) => Array.isArray(value) && value.length ? <Space direction="vertical">{value.map((action, index) => <span key={index}>{automationActionText(action)}</span>)}</Space> : '未配置动作' },
      { title: '重复间隔', dataIndex: 'cooldown_days', render: (value: number) => value ? `${value} 天` : '未设置' },
      { title: '原配置状态', dataIndex: 'is_enabled', render: (value: boolean) => <Tag>{value ? '标记为启用 · 执行待核验' : '停用'}</Tag> },
      { title: '操作', render: (_: unknown, row: any) => <Button type="link" onClick={() => void loadLogs(row)}>查看记录</Button> },
    ]} /></Card></>}
    <Modal open={open} title="保存一条停用的标签规则" onCancel={close} footer={null} maskClosable={false}><Form form={form} layout="vertical" initialValues={{ action: 'add_tag', trigger_event: 'order_completed', cooldown_days: 0 }} onValuesChange={() => setDirty(true)} onFinish={async values => { if (busy.current || !canConfigure) return; busy.current = true; setSaving(true); try { await createAutomation(disabledTagRule(values), storeId); message.success('规则已保存为停用，未执行动作'); setOpen(false); setDirty(false); await load(); } catch (err) { setSaveError(requestErrorMessage(err)); } finally { busy.current = false; setSaving(false); } }}>
      {saveError && <Alert type="error" message="尚未确认创建结果，请关闭并刷新列表核对后再操作" description={saveError} />}
      <Form.Item name="name" label="规则名称" rules={[{ required: true, whitespace: true }, { max: 64 }]}><Input maxLength={64} /></Form.Item>
      <Form.Item name="trigger_event" label="触发条件" rules={[{ required: true }]}><Select options={Object.entries(TRIGGER_LABELS).map(([value,label]) => ({ value,label }))} /></Form.Item>
      <Form.Item name="action" label="计划动作" rules={[{ required: true }]}><Select options={['add_tag','remove_tag'].map(value => ({ value,label: ACTION_LABELS[value] }))} /></Form.Item>
      <Form.Item name="tag_id" label="本店标签" rules={[{ required: true }]} extra="仅选择已存在的标签，本次保存不会给顾客打标。"><Select options={tags.filter(tag => tag.status === 'active').map(tag => ({ value: tag.id,label: tag.name }))} /></Form.Item>
      <Form.Item name="cooldown_days" label="同一顾客重复执行间隔（天）"><InputNumber min={0} max={3650} precision={0} /></Form.Item>
      <Form.Item name="description" label="用途说明"><Input.TextArea maxLength={256} rows={2} /></Form.Item><Space><Button disabled={saving} onClick={close}>取消</Button><Button type="primary" htmlType="submit" loading={saving} disabled={!!saveError}>保存为停用</Button></Space>
    </Form></Modal>
    <Modal title={`执行记录 · ${logRule?.name || ''}`} open={!!logRule} onCancel={() => { logSequence.current++; setLogRule(undefined); }} footer={<Button onClick={() => { logSequence.current++; setLogRule(undefined); }}>关闭</Button>} width={760}>
      {logError && <Alert type="error" message="执行记录读取失败" description={logError} action={<Button onClick={() => void loadLogs(logRule, logPage)}>重试</Button>} />}
      <Table rowKey="id" loading={logLoading} dataSource={logs} pagination={{ current: logPage, pageSize: 20, total: logTotal, showSizeChanger: false, onChange: page => void loadLogs(logRule,page) }} locale={{ emptyText: logError ? '读取未完成' : '暂无执行记录；不能据此认定规则已运行' }} columns={[{ title: '时间', dataIndex: 'created_at', render: (value: string) => value ? new Date(value).toLocaleString('zh-CN') : '—' }, { title: '顾客', render: (_: unknown,row: any) => row.customer || row.phone_masked || '未关联顾客' }, { title: '动作', dataIndex: 'action_type', render: (value: string) => ACTION_LABELS[value] || '旧版动作' }, { title: '记录结果', dataIndex: 'success', render: (value: boolean) => value ? '成功' : '失败，需核查处理记录' }]} />
    </Modal></div>;
}
