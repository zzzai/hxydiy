import { detailIntroduction } from '../detailIntroduction';

export default function DetailIntroduction(props: Parameters<typeof detailIntroduction>[0]) {
  const { summary, highlights, facts } = detailIntroduction(props);
  return <>
    {highlights.length > 0 && <div className="mini-detail-tags detail-intro-highlights" aria-label="项目特色">{highlights.map((tag) => <span key={tag}>{tag}</span>)}</div>}
    <p className="detail-intro-copy">{summary}</p>
    {facts.length > 0 && <p className="detail-intro-facts">{facts.join(' · ')}</p>}
  </>;
}
