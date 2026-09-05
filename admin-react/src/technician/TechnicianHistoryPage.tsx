import TechnicianServiceHistoryPage from './TechnicianServiceHistoryPage';


export default function TechnicianHistoryPage() {
  return <div className="technician-history-page">
    <div className="technician-page-title"><div><span className="technician-eyebrow">本人服务</span><h1>历史服务</h1><p>仅展示由本人实际完成的服务</p></div></div>
    <TechnicianServiceHistoryPage />
  </div>;
}

