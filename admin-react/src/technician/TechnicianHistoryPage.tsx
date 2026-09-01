import ServiceOrderList from '../features/technician/ServiceOrderList';


export default function TechnicianHistoryPage() {
  return <div className="technician-history-page">
    <div className="technician-page-title"><div><span className="technician-eyebrow">当前门店</span><h1>历史服务单</h1><p>查看本店已完成或已取消服务</p></div></div>
    <ServiceOrderList defaultStatus="history" pageSize={20} />
  </div>;
}

