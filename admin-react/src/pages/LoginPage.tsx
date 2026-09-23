import { useState } from 'react';
import { App, Form, Input, Button, Card, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { login, selectStaffWorkspace } from '../api';
import { isTechnicianEntry } from '../auth';
import { finishWorkspaceSelection, interpretStaffLogin, storeStaffSession, type WorkspaceGrant, type WorkspaceSelection } from '../workspaceLogin';

const { Title, Text } = Typography;

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState<WorkspaceSelection | null>(null);

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await login(values.username, values.password);
      const step = interpretStaffLogin(res.data);
      if (step.kind === 'select') {
        localStorage.removeItem('hxy_admin_token');
        localStorage.removeItem('hxy_admin_staff');
        setSelection(step);
        return;
      }
      storeStaffSession(localStorage, step);
      if (step.staff.role === 'technician') {
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
    } catch (error) {
      if (error instanceof Error && !('response' in error)) message.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const chooseWorkspace = async (workspace: WorkspaceGrant) => {
    if (!selection || loading) return;
    setLoading(true);
    try {
      const res = await selectStaffWorkspace(workspace.assignment_id, selection.selectorToken);
      storeStaffSession(localStorage, finishWorkspaceSelection(res.data, workspace.assignment_id));
      message.success('已进入工作区');
      onLogin();
    } catch (error) {
      setSelection(null);
      if (error instanceof Error && !('response' in error)) message.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #1f8f75, #0f4f43)' }}>
      <Card style={{ width: 380, maxWidth: 'calc(100vw - 32px)', borderRadius: 16, boxShadow: '0 12px 40px rgba(0,0,0,.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={2} style={{ color: '#1f8f75', marginBottom: 4 }}>荷小悦</Title>
          <Text type="secondary">{selection ? '请选择进入的工作区' : '门店管理中台'}</Text>
        </div>
        {selection ? <div style={{ display: 'grid', gap: 12 }}>
          {selection.workspaces.map((workspace) => <Button
            key={workspace.assignment_id}
            block
            size="large"
            loading={loading}
            onClick={() => void chooseWorkspace(workspace)}
          >
            {workspace.scope_name} · {workspace.role === 'brand_admin' ? '品牌管理员' : workspace.role === 'hq_operator' ? '总部运营' : workspace.role === 'store_manager' ? '店长' : '门店员工'}
          </Button>)}
          <Button type="link" disabled={loading} onClick={() => setSelection(null)}>返回登录</Button>
        </div> : <Form onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入账号' }]}>
            <Input prefix={<UserOutlined />} placeholder="账号" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>登 录</Button>
          </Form.Item>
        </Form>}
      </Card>
    </div>
  );
}
