import { customerProjectSummaryText, type Project } from '../domain';
import { packageSessionExplanation } from '../projectDetailGuidance';

export default function ProjectServiceNotes({ project, basePrice }: { project: Project; basePrice: number }) {
  const isKit = project.code === 'hxy-taoke-60';
  const sessions = isKit ? packageSessionExplanation(project, basePrice) : null;
  const missingDuration = !project.duration_min && !/\d+\s*分钟/.test(customerProjectSummaryText(project));
  if (!isKit && !missingDuration) return null;

  return (
    <aside className="detail-service-notes" aria-label="购买前了解">
      {isKit ? <>
        {sessions && <p className="detail-session-price"><strong>约 ¥{sessions.average}/次</strong><span>按{sessions.count}次整套价格折算，非单次售价</span></p>}
        <p><strong>无有效期</strong> · 按整套购买，分次使用。</p>
        <p>购买前请与前台确认预约、核销和售后规则；涉及退费的，依法处理。</p>
      </> : <p>服务时长与具体安排，请在开始前向前台确认。</p>}
    </aside>
  );
}
