import React from 'react';
import ReactDOM from 'react-dom/client';
import { MotionConfig } from 'framer-motion';

import { isReportEntry } from './returnEntry';
import './styles.css';

const RoomDoorPage = React.lazy(() => import('./components/RoomDoorPage'));
const App = React.lazy(() => import('./App'));
const ReportEntryPage = React.lazy(() => import('./components/ReportEntryPage'));
const StoreFeedbackPage = React.lazy(() => import('./components/StoreFeedbackPage'));
const CouponClaimPage = React.lazy(() => import('./components/CouponClaimPage'));
const params = new URLSearchParams(window.location.search);
const roomDoor = params.get('door');
const feedbackEntry = params.get('view') === 'feedback';
const couponClaimEntry = params.has('c') || params.get('view') === 'coupon-claim';
const reportEntry = isReportEntry(params);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <React.Suspense fallback={<p role="status">{roomDoor !== null ? '正在打开房间…' : feedbackEntry ? '正在打开评价…' : couponClaimEntry ? '正在打开半价券…' : reportEntry ? '正在打开本人报告…' : '正在打开菜单…'}</p>}>
        {roomDoor !== null ? <RoomDoorPage code={roomDoor} /> : feedbackEntry ? <StoreFeedbackPage /> : couponClaimEntry ? <CouponClaimPage /> : reportEntry ? <ReportEntryPage /> : <App />}
      </React.Suspense>
    </MotionConfig>
  </React.StrictMode>,
);
