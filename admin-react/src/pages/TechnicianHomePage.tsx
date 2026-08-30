import { Card, Space, Typography } from 'antd';
import ServiceOrderList from '../features/technician/ServiceOrderList';

export default function TechnicianHomePage() {
  return <Space direction="vertical" size={16} style={{ width: '100%' }}><div><Typography.Title level={3} style={{ margin: 0 }}>技师服务单</Typography.Title><Typography.Text type="secondary">查看当前门店全部服务单，手机号和价格信息已脱敏</Typography.Text></div><Card><ServiceOrderList /></Card></Space>;
}
