/** 仅整理展示，不修改项目标签来源或业务规则。 */
export function detailIntroduction(input: {
  name: string; summary: string; highlights: string[]; facts?: string[]; duration?: number | null;
}) {
  const normalize = (text: string) => text.replace(/[\s+＋·、，,。/]/g, '').toLowerCase();
  const summary = input.summary.replace(/[+＋]/g, ' · ');
  const described = normalize(input.name + summary);
  const highlights = [...new Set(input.highlights)].filter((tag) => !described.includes(normalize(tag))).slice(0, 2);
  const facts = [...new Set(input.facts || [])].filter((tag) =>
    !['单次服务', '可多选', '可自由搭配', '可按需加选', '可搭配局部加强'].includes(tag)
    && !described.includes(normalize(tag)) && !highlights.includes(tag));
  if (input.duration && !described.includes(`${input.duration}分钟`) && !facts.some((tag) => tag.includes(`${input.duration}分钟`))) {
    facts.unshift(`${input.duration}分钟`);
  }
  return { summary, highlights, facts };
}
