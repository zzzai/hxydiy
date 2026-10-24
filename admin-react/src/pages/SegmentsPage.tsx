import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, Modal, Select, Space, Spin, Switch, Tag } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { getSegments, createSegment, recountSegment, getTags } from '../api';
import { getStaff } from '../api';
import { requestErrorMessage } from '../requestError';
import { segmentConditions, segmentSummary } from '../businessDisplay';

export default function SegmentsPage() {
  const { message, modal } = App.useApp();
  const staff = getStaff();
  const [data, setData] = useState<any[]>([]), [tags, setTags] = useState<any[]>([]);
  const [loading, setLoading] = useState(false), [error, setError] = useState(''), [saveError, setSaveError] = useState('');
  const [open, setOpen] = useState(false), [dirty, setDirty] = useState(false), [saving, setSaving] = useState(false), [recounting, setRecounting] = useState<number>();
  const busy = useRef(false), sequence = useRef(0);
  const [form] = Form.useForm();
  const canWrite = ['admin', 'manager'].includes(staff?.role || '');
  const load = async () => { const request = ++sequence.current; setLoading(true); setError(''); try { const [rows, availableTags] = await Promise.all([getSegments(), getTags()]); if (request !== sequence.current) return; setData(rows.data || []); setTags(availableTags.data || []); } catch (err) { if (request === sequence.current) setError(requestErrorMessage(err)); } finally { if (request === sequence.current) setLoading(false); } };
  useEffect(() => { if (staff?.store_id) void load(); return () => { sequence.current++; }; }, [staff?.store_id]);
  const close = () => { if (saving) return; if (dirty) modal.confirm({ title: '分群还未保存', content: '关闭会放弃本次填写。已有分群不会变化。', okText: '放弃填写', cancelText: '继续编辑', onOk: () => { setOpen(false); setDirty(false); } }); else setOpen(false); };
  if (!staff?.store_id) return <><div className="page-heading"><div><h2>顾客分群</h2><div className="page-kicker">按本店标签与会员标记整理顾客</div></div></div><Alert type="info" showIcon message="请先进入门店工作区" description="分群接口按登录账号所属门店核验权限。总部视图不能直接代替门店工作区，避免误查或误写其他门店。" /></>;
  return <div><div className="page-heading"><div><h2>顾客分群</h2><div className="page-kicker">{staff.store_name || '当前门店'} · 仅整理分组，不发送消息或发券</div></div><Space><Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>{canWrite && <Button type="primary" icon={<PlusOutlined />} disabled={!!error || loading} onClick={() => { form.resetFields(); setSaveError(''); setDirty(false); setOpen(true); }}>新建分群</Button>}</Space></div>
    {error && <Alert type="error" showIcon message="分群读取失败" description={error} action={<Button onClick={() => void load()}>重试</Button>} style={{ marginBottom: 16 }} />}
    <Spin spinning={loading}>{!data.length && !error && !loading && <Card><Empty description="本店还没有顾客分群，可按实际运营需要建立" /></Card>}{data.map(row => <Card key={row.id} style={{ marginBottom: 16 }} title={row.name} extra={<Tag>{row.user_count} 人 · 上次统计</Tag>}><p>{row.description || '未填写说明'}</p><Space wrap>{segmentSummary(row.conditions).map(text => <Tag key={text}>{text}</Tag>)}</Space><p style={{ color: '#536158' }}>同一组标签按“任一标签”匹配；会员标记不等同于当前可用权益。</p>{canWrite && <Button loading={recounting === row.id} disabled={recounting !== undefined} onClick={async () => { setRecounting(row.id); try { await recountSegment(row.id); message.success('本店人数已更新'); await load(); } catch (err) { message.error(requestErrorMessage(err)); } finally { setRecounting(undefined); } }}>更新人数</Button>}</Card>)}</Spin>
    <Modal title="建立本店顾客分群" open={open} onCancel={close} maskClosable={false} footer={null} width={600}><Form form={form} layout="vertical" onValuesChange={() => setDirty(true)} onFinish={async values => { if (busy.current) return; busy.current = true; setSaving(true); setSaveError(''); try { await createSegment({ name: values.name.trim(), description: values.description || '', conditions: segmentConditions(values) }); message.success('分群已保存，请更新人数核对范围'); setOpen(false); setDirty(false); await load(); } catch (err) { setSaveError(`${requestErrorMessage(err)} 如未确认创建结果，请先关闭并刷新列表核对，避免重复创建。`); } finally { busy.current = false; setSaving(false); } }}>
      {saveError && <Alert type="error" message="尚未确认保存结果" description={saveError} style={{ marginBottom: 16 }} />}
      <Form.Item name="name" label="分群名称" rules={[{ required: true, whitespace: true }, { max: 64 }]}><Input maxLength={64} placeholder="例如：有肩颈服务偏好的顾客" /></Form.Item>
      <Form.Item name="description" label="使用说明"><Input.TextArea maxLength={256} rows={2} /></Form.Item>
      <Form.Item name="tags" label="顾客标签" extra="匹配所选任一标签；不选则不限标签。"><Select mode="multiple" options={tags.filter(tag => tag.status === 'active').map(tag => ({ value: tag.name, label: tag.name }))} placeholder="选择本店已有标签" /></Form.Item>
      <Form.Item name="memberOnly" label="只包含有会员标记的顾客" valuePropName="checked" extra="使用现有会员标记，不代表当前仍有有效年卡或余额。"><Switch /></Form.Item>
      <Space><Button onClick={close} disabled={saving}>取消</Button><Button type="primary" htmlType="submit" loading={saving} disabled={!!saveError}>保存分群</Button></Space>
    </Form></Modal></div>;
}
