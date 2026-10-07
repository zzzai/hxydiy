import { Alert } from 'antd';

export default function TechnicianMembershipPausedPage() {
  return <section className="technician-member-paused">
    <h1>会员码核验暂未开放</h1>
    <Alert type="info" showIcon message="当前无需在移动工作台核验会员码" description="会员身份与价格仍按门店现有规则处理。" />
  </section>;
}
