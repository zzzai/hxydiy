import TechnicianServiceHistoryPage from './TechnicianServiceHistoryPage';


export default function TechnicianHistoryPage() {
  return <div className="technician-history-page">
    <div className="technician-page-title"><div><h1>服务记录</h1><p>仅展示由本人实际完成的服务</p></div></div>
    <TechnicianServiceHistoryPage />
  </div>;
}

