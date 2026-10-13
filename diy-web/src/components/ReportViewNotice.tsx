export default function ReportViewNotice({ notice, actionLabel }: { notice: string; actionLabel?: string }) {
  return <section className="report-entry-notice" aria-label="本人报告查看说明">
    <p>仅按已验证手机号查询本人报告，将前往检测方原站。报告可能包含个人及健康信息，链接持有人可查看，请勿转发。</p>
    <p>DIY不向原站传递手机号、登录令牌或读取密钥，不复制报告图片、不向员工开放、不用于推送或新增诊断。</p>
    <p>撤回DIY查看授权，不能使已取得或已转发的原站链接失效。</p>
    <details><summary>完整查看说明</summary><p>{notice}</p></details>
    {actionLabel && <p>点击“{actionLabel}”，即单独同意上述本人报告查看及原站跳转说明。</p>}
  </section>;
}
