import { useEffect, useState } from 'react';
import { Button, Card, Form, Input, List, Modal, Popconfirm, Space, Switch, Typography, message } from 'antd';
import { getPageContent, getPageContentVersions, rollbackPageContent, updatePageContent } from '../api';
import StoreScopeSelect from '../components/StoreScopeSelect';

const json = (value: unknown) => JSON.stringify(value ?? [], null, 2);

export default function PageContentPage() {
  const [form] = Form.useForm();
  const [storeId, setStoreId] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [versionOpen, setVersionOpen] = useState(false);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await getPageContent('diy-home', storeId);
      form.setFieldsValue({ ...data, promo_banners: json(data.promo_banners), tea_options: json(data.tea_options), coupon_prompt: json(data.coupon_prompt), brand_story: json(data.brand_story) });
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [storeId]);

  const openVersions = async () => {
    setVersionOpen(true); setVersionLoading(true); setVersions([]);
    try {
      const response = await getPageContentVersions('diy-home', storeId);
      setVersions(response.data?.items || []);
    } catch { message.error('版本记录加载失败'); }
    finally { setVersionLoading(false); }
  };

  const rollback = async (versionId: number) => {
    setVersionLoading(true);
    try {
      await rollbackPageContent(versionId, 'diy-home', storeId);
      message.success('已回滚并发布该版本');
      setVersionOpen(false);
      await load();
    } catch { message.error('回滚失败，请稍后重试'); }
    finally { setVersionLoading(false); }
  };

  const save = async (values: any) => {
    setSaving(true);
    try {
      const payload = { ...values, promo_banners: JSON.parse(values.promo_banners || '[]'), tea_options: JSON.parse(values.tea_options || '[]'), coupon_prompt: JSON.parse(values.coupon_prompt || '{}'), brand_story: JSON.parse(values.brand_story || '{}') };
      await updatePageContent('diy-home', payload, storeId);
      message.success('页面内容已保存');
    } catch (error) { message.error(error instanceof SyntaxError ? 'JSON 格式不正确' : '保存失败，请检查后重试'); }
    finally { setSaving(false); }
  };
  return <Card title="DIY 页面配置" loading={loading} extra={<Space><StoreScopeSelect value={storeId} onChange={setStoreId} /><Button onClick={() => void openVersions()}>版本记录</Button><Typography.Text type="secondary">仅发布内容会显示在顾客端</Typography.Text></Space>}>
    <Form form={form} layout="vertical" onFinish={save}>
      <Space wrap style={{ width: '100%' }}><Form.Item name="title" label="页面标题" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="subtitle" label="页面副标题"><Input /></Form.Item><Form.Item name="published" label="发布" valuePropName="checked"><Switch /></Form.Item></Space>
      <Form.Item name="promo_banners" label="推荐 Banner 配置（JSON）"><Input.TextArea rows={5} /></Form.Item>
      <Form.Item name="tea_options" label="三种茶饮配置（JSON）"><Input.TextArea rows={8} /></Form.Item>
      <Form.Item name="coupon_prompt" label="优惠券提示（JSON）"><Input.TextArea rows={4} /></Form.Item>
      <Form.Item name="brand_story" label="品牌故事（JSON）"><Input.TextArea rows={4} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={saving}>保存并发布配置</Button>
    </Form>
    <Modal title="页面发布版本" open={versionOpen} onCancel={() => setVersionOpen(false)} footer={<Button onClick={() => setVersionOpen(false)}>关闭</Button>} width={640}>
      <List
        loading={versionLoading}
        dataSource={versions}
        locale={{ emptyText: '还没有发布过版本；打开发布并保存后会生成第一个版本。' }}
        renderItem={(version: any) => <List.Item actions={[
          <Popconfirm key="rollback" title="确认回滚并重新发布该版本？" onConfirm={() => void rollback(version.id)}>
            <Button size="small" type="link">回滚到此版本</Button>
          </Popconfirm>,
        ]}>
          <List.Item.Meta
            title={`v${version.version_no} · ${version.title || '未命名页面'}`}
            description={`${version.created_by || '系统'} · ${version.created_at?.slice(0, 19).replace('T', ' ') || '-'}`}
          />
        </List.Item>}
      />
    </Modal>
  </Card>;
}
