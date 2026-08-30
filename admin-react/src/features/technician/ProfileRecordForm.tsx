import { useEffect } from 'react';
import { App, Button, Form, Input, Modal, Select } from 'antd';
import { createProfileRecord } from '../../api';

type ProfileRecordFormProps = {
  customerId?: number;
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
};

const TAG_OPTIONS = ['久坐', '肩颈紧张', '腰背疲劳', '睡眠关注', '放松需求', '偏好轻柔力度', '偏好中等力度'];

export default function ProfileRecordForm({ customerId, open, onClose, onSaved }: ProfileRecordFormProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  useEffect(() => { if (!open) form.resetFields(); }, [form, open]);

  const submit = async (values: { tags?: string[]; service_note?: string }) => {
    if (!customerId) return;
    try {
      await createProfileRecord(customerId, { tags: values.tags || [], service_note: values.service_note || '' });
      message.success('顾客画像已记录');
      onSaved?.();
      onClose();
    } catch {
      // API interceptor provides the server error; retain values for retry.
    }
  };

  return <Modal title="新增顾客画像记录" open={open} onCancel={onClose} footer={<Button type="primary" onClick={() => form.submit()}>保存记录</Button>}>
    <Form form={form} layout="vertical" onFinish={submit}>
      <Form.Item name="tags" label="服务观察标签"><Select mode="tags" options={TAG_OPTIONS.map((value) => ({ value, label: value }))} maxTagCount={8} /></Form.Item>
      <Form.Item name="service_note" label="服务备注" rules={[{ max: 1000, message: '备注不能超过 1000 个字符' }]}><Input.TextArea rows={5} maxLength={1000} showCount placeholder="仅记录顾客自述和服务观察，不填写诊断、治疗或治愈结论" /></Form.Item>
    </Form>
  </Modal>;
}

