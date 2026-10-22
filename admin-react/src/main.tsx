import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntApp, ConfigProvider } from 'antd';
import App from './App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#16705c',
          colorInfo: '#2f6e9b',
          colorSuccess: '#1f8f75',
          colorWarning: '#a86f1f',
          colorError: '#b54532',
          colorTextBase: '#132a24',
          colorBgBase: '#f3f7f4',
          colorBgLayout: '#f3f7f4',
          colorBorder: '#dee9e3',
          colorSplit: '#edf2ef',
          borderRadius: 10,
          borderRadiusLG: 12,
          controlHeight: 38,
          fontFamily: '"Avenir Next", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
          boxShadow: '0 12px 32px rgba(15, 45, 36, .12)',
        },
        components: {
          Layout: { bodyBg: '#f3f7f4', headerBg: '#ffffff', siderBg: '#0b2822' },
          Menu: {
            darkItemBg: '#0b2822',
            darkSubMenuItemBg: '#0b2822',
            darkItemColor: '#c7d7d0',
            darkGroupTitleColor: '#7e9b90',
            darkItemSelectedBg: '#145545',
            darkItemSelectedColor: '#ffffff',
            itemHeight: 40,
            itemBorderRadius: 8,
          },
          Table: {
            headerBg: '#f7faf8',
            headerColor: '#647a71',
            borderColor: '#edf2ef',
            headerSplitColor: 'transparent',
            rowHoverBg: '#f5faf7',
          },
          Button: { primaryShadow: 'none', defaultShadow: 'none' },
          Card: { borderRadiusLG: 12 },
          Drawer: { footerPaddingBlock: 12 },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
