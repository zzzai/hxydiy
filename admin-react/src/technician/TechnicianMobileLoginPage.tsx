import { useState } from 'react';
import { App, Button, Form, Input, Typography } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { activateTechnician, login } from '../api';

type LoginValues = { username?: string; password: string; token?: string; confirmPassword?: string };

export default function TechnicianMobileLoginPage({ onLogin }: { onLogin: (staff: any) => void }) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'login' | 'activate'>('login');
  const submit = async (values: LoginValues) => {
    setLoading(true);
    try {
      if (mode === 'activate') {
        if (values.password !== values.confirmPassword) {
          message.error('两次输入的密码不一致');
          return;
        }
        const response = await activateTechnician(values.token || '', values.password);
        localStorage.setItem('hxy_admin_token', response.data.token);
        localStorage.setItem('hxy_admin_staff', JSON.stringify(response.data.staff));
        onLogin(response.data.staff);
        return;
      }
      const response = await login(values.username || '', values.password);
      if (!['technician', 'manager'].includes(response.data.staff?.role)) {
        message.error('该账号没有移动端会员核验权限');
        return;
      }
      localStorage.setItem('hxy_admin_token', response.data.token);
      localStorage.setItem('hxy_admin_staff', JSON.stringify(response.data.staff));
      onLogin(response.data.staff);
    } catch {
      // API interceptor displays the server error.
    } finally {
      setLoading(false);
    }
  };

  return <main className="technician-login-page">
    <section className="technician-login-card">
      <div className="technician-login-brand"><span>荷</span><div><Typography.Title level={2}>门店移动工作台</Typography.Title><Typography.Text>技师服务与会员核验</Typography.Text></div></div>
      <Form layout="vertical" size="large" onFinish={submit} preserve>
        {mode === 'login' ? <>
          <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}><Input prefix={<UserOutlined />} placeholder="请输入技师或店长账号" autoComplete="username" /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}><Input.Password prefix={<LockOutlined />} placeholder="请输入密码" autoComplete="current-password" /></Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading} className="technician-primary-button">登录移动工作台</Button>
          <Button type="link" block onClick={() => setMode('activate')}>首次激活 / 重置密码</Button>
        </> : <>
          <Form.Item name="token" label="激活凭证" rules={[{ required: true, message: '请输入店长提供的激活凭证' }]}><Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} placeholder="粘贴店长提供的一次性凭证" /></Form.Item>
          <Form.Item name="password" label="新密码" rules={[{ required: true, min: 8, message: '密码至少 8 位' }]}><Input.Password prefix={<LockOutlined />} placeholder="设置新密码" autoComplete="new-password" /></Form.Item>
          <Form.Item name="confirmPassword" label="确认密码" rules={[{ required: true, message: '请再次输入新密码' }]}><Input.Password prefix={<LockOutlined />} placeholder="再次输入新密码" autoComplete="new-password" /></Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading} className="technician-primary-button">完成激活</Button>
          <Button type="link" block onClick={() => setMode('login')}>返回账号登录</Button>
        </>}
      </Form>
    </section>
  </main>;
}
