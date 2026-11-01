import React from 'react';
import ReactDOM from 'react-dom/client';
import axios, { AxiosError } from 'axios';
import { App, ConfigProvider } from 'antd';
import { client } from '../src/api';
import { writeStaffSession } from '../src/staffSession';
import TechnicianMobileApp from '../src/technician/TechnicianMobileApp';
import '../src/styles.css';
import '../src/technician/technician-mobile.css';

const params = new URLSearchParams(location.search);
const actor = params.get('actor') || sessionStorage.getItem('learning-formal-actor') || 'tech-a';
if (!['tech-a','tech-b','manager','other'].includes(actor)) throw new Error('Unknown synthetic identity');
sessionStorage.setItem('learning-formal-actor',actor);
const response = await fetch('/__learning_preview__/session?actor='+encodeURIComponent(actor),{cache:'no-store'});
if(!response.ok)throw new Error('Synthetic session unavailable');
const session = await response.json();
for(const key of ['hxy_admin_token','hxy_admin_staff','hxy_staff_auth_method','hxy_technician_token','hxy_technician_staff','hxy_technician_auth_method']) localStorage.removeItem(key);
sessionStorage.removeItem('hxy_wecom_pending');
writeStaffSession(localStorage,{token:session.token,staff:session.staff,authMethod:'password'});
const transport = axios.getAdapter('xhr');
client.defaults.adapter = async config => {
 if(config.url?.startsWith('/staff-learning/') || config.method==='get') return transport(config);
 throw new AxiosError('Only learning writes are allowed in this preview','ERR_BAD_REQUEST',config);
};
const width=Number(params.get('width'))||375;
document.documentElement.style.setProperty('--formal-width',`${[320,375,390,430].includes(width)?width:375}px`);
const style=document.createElement('style');style.textContent=`html{scrollbar-width:none}body{margin:0;background:#eaf0ed}#root{max-width:var(--formal-width);margin:auto;min-height:100vh;background:#fff}.formal-banner{padding:8px 16px;color:#4c6255;background:#f0f5f1;font:12px/1.6 sans-serif}.formal-banner select{margin-left:10px;min-height:32px}.technician-mobile-tabbar{max-width:var(--formal-width);margin:auto}.technician-mobile-shell{min-height:calc(100vh - 64px)}`;document.head.appendChild(style);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ConfigProvider theme={{token:{colorPrimary:'#245B42',colorBgContainer:'#ffffff',borderRadius:12}}}><App><aside className="formal-banner">隔离验收 · 合成数据 · 未发布<label><select aria-label="预览身份" value={actor} onChange={e=>location.assign('/technician/'+(e.target.value==='manager'?'store':'today')+'?actor='+e.target.value+'&width='+width)}><option value="tech-a">技师 A</option><option value="tech-b">技师 B</option><option value="manager">店长</option><option value="other">异店技师</option></select></label></aside><TechnicianMobileApp/></App></ConfigProvider></React.StrictMode>);
