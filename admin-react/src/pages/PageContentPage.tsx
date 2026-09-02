import { useEffect, useState } from 'react';
import { Button, Card, Form, Input, Space, Switch, Typography, message } from 'antd';
import { getPageContent, updatePageContent } from '../api';

const json = (value: unknown) => JSON.stringify(value ?? [], null, 2);

export default function PageContentPage() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const { data } = await getPageContent();
      form.setFieldsValue({ ...data, promo_banners: json(data.promo_banners), tea_options: json(data.tea_options), coupon_prompt: json(data.coupon_prompt), brand_story: json(data.brand_story) });
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const save = async (values: any) => {
    setSaving(true);
    try {
      const payload = { ...values, promo_banners: JSON.parse(values.promo_banners || '[]'), tea_options: JSON.parse(values.tea_options || '[]'), coupon_prompt: JSON.parse(values.coupon_prompt || '{}'), brand_story: JSON.parse(values.brand_story || '{}') };
      await updatePageContent('diy-home', payload);
      message.success('页面内容已保存');
    } catch (error) { message.error(error instanceof SyntaxError ? 'JSON 格式不正确' : '保存失败，请检查后重试'); }
    finally { setSaving(false); }
  };
  return <Card title="DIY 页面配置" loading={loading} extra={<Typography.Text type="secondary">仅发布内容会显示在顾客端</Typography.Text>}>
    <Form form={form} layout="vertical" onFinish={save}>
      <Space wrap style={{ width: '100%' }}><Form.Item name="title" label="页面标题" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="subtitle" label="页面副标题"><Input /></Form.Item><Form.Item name="published" label="发布" valuePropName="checked"><Switch /></Form.Item></Space>
      <Form.Item name="promo_banners" label="推荐 Banner 配置（JSON）"><Input.TextArea rows={5} /></Form.Item>
      <Form.Item name="tea_options" label="三种茶饮配置（JSON）"><Input.TextArea rows={8} /></Form.Item>
      <Form.Item name="coupon_prompt" label="优惠券提示（JSON）"><Input.TextArea rows={4} /></Form.Item>
      <Form.Item name="brand_story" label="品牌故事（JSON）"><Input.TextArea rows={4} /></Form.Item>
      <Button type="primary" htmlType="submit" loading={saving}>保存并发布配置</Button>
    </Form>
  </Card>;
}
