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
          colorPrimary: '#197A3B',
          colorPrimaryHover: '#166B34',
          colorPrimaryActive: '#135C2C',
          colorInfo: '#245A81',
          colorSuccess: '#197A3B',
          colorWarning: '#8A5200',
          colorError: '#B42318',
          colorTextBase: '#202A23',
          colorTextSecondary: '#536158',
          colorTextTertiary: '#667369',
          colorBgBase: '#FFFFFF',
          colorBgLayout: '#F6F8F6',
          colorBorder: '#DCE4DC',
          colorBorderSecondary: '#DCE4DC',
          colorSplit: '#DCE4DC',
          colorLink: '#197A3B',
          colorLinkHover: '#166B34',
          controlOutline: 'rgba(25, 122, 59, .14)',
          borderRadius: 10,
          borderRadiusLG: 12,
          controlHeight: 38,
          fontFamily: '"Avenir Next", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
          boxShadow: '0 12px 32px rgba(32, 42, 35, .12)',
        },
        components: {
          Layout: { bodyBg: '#F6F8F6', headerBg: '#FFFFFF', siderBg: '#FFFFFF' },
          Menu: {
            itemBg: '#FFFFFF',
            subMenuItemBg: '#FFFFFF',
            itemColor: '#536158',
            groupTitleColor: '#667369',
            itemHoverBg: '#F1F7F3',
            itemHoverColor: '#197A3B',
            itemSelectedBg: '#E3EFE7',
            itemSelectedColor: '#197A3B',
            itemHeight: 42,
            itemBorderRadius: 8,
          },
          Table: {
            headerBg: '#F6F8F6',
            headerColor: '#536158',
            borderColor: '#DCE4DC',
            headerSplitColor: 'transparent',
            rowHoverBg: '#F1F7F3',
          },
          Button: { primaryShadow: 'none', defaultShadow: 'none', primaryColor: '#FFFFFF' },
          Card: { borderRadiusLG: 12 },
          Drawer: { footerPaddingBlock: 12 },
          Tag: { defaultBg: '#F6F8F6', defaultColor: '#536158' },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
