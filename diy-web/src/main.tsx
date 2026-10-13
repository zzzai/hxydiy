import React from 'react';
import ReactDOM from 'react-dom/client';
import { MotionConfig } from 'framer-motion';

import App from './App';
import { isReportEntry } from './returnEntry';
import './styles.css';

const ReportEntryPage = React.lazy(() => import('./components/ReportEntryPage'));

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <React.Suspense fallback={<p role="status">正在打开本人报告…</p>}>
        {isReportEntry(new URLSearchParams(window.location.search)) ? <ReportEntryPage /> : <App />}
      </React.Suspense>
    </MotionConfig>
  </React.StrictMode>,
);
