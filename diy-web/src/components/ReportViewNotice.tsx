export default function ReportViewNotice({ notice, actionLabel, login = false }: { notice: string; actionLabel?: string; login?: boolean }) {
  return <section className="report-entry-notice" aria-label="本人报告查看说明">
    <p>仅查看本人报告</p>
    <details>
      <summary>{(login || actionLabel) && <span className="report-view-agreement">{login ? '登录' : '查看'}即表示同意</span>}<span className="report-view-notice-link">报告查看说明</span></summary>
      <div className="report-view-notice-text" tabIndex={0} aria-label="完整报告查看说明"><p>{notice}</p></div>
    </details>
  </section>;
}
