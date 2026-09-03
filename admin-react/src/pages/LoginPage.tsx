import { useState } from 'react';
import { App, Form, Input, Button, Card, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { login } from '../api';
import { isTechnicianEntry } from '../auth';

const { Title, Text } = Typography;

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await login(values.username, values.password);
      localStorage.setItem('hxy_admin_token', res.data.token);
      localStorage.setItem('hxy_admin_staff', JSON.stringify(res.data.staff));
      if (res.data.staff?.role === 'technician') {
        window.location.replace('/technician/today');
        return;
      }
      if (isTechnicianEntry()) {
        localStorage.removeItem('hxy_admin_token');
        localStorage.removeItem('hxy_admin_staff');
        message.error('请使用技师账号登录');
        return;
      }
      message.success('登录成功');
      onLogin();
    } catch {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #1f8f75, #0f4f43)' }}>
      <Card style={{ width: 380, borderRadius: 16, boxShadow: '0 12px 40px rgba(0,0,0,.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={2} style={{ color: '#1f8f75', marginBottom: 4 }}>荷小悦</Title>
          <Text type="secondary">门店管理中台</Text>
        </div>
        <Form onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入账号' }]}>
            <Input prefix={<UserOutlined />} placeholder="账号" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>登 录</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
