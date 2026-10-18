import React from 'react';
import ReactDOM from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import TechnicianMobileApp from '../src/technician/TechnicianMobileApp';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ConfigProvider><App><TechnicianMobileApp /></App></ConfigProvider></React.StrictMode>,
);
