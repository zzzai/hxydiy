import React from 'react';
import { ChevronRight } from 'lucide-react';
import type { ProjectDetailVisualSection } from '../projectDetailVisuals';

export default function ProjectDetailVisualSections({ sections, eyebrow, title }: {
  sections: ProjectDetailVisualSection[];
  eyebrow?: string;
  title?: string;
}) {
  if (sections.length === 0) return null;

  return (
    <section className="project-detail-visuals" aria-label="项目体验介绍">
      <header>
        <span>{eyebrow || '服务体验'}</span>
        <h2>{title || '服务怎么安排'}</h2>
      </header>
      <div className="detail-experience-copy">
        {sections.map((section) => (
          <article key={section.image}>
            <h3>{section.title}</h3>
            <p>{section.body}</p>
          </article>
        ))}
      </div>
      <details className="detail-illustration-gallery">
        <summary>看看服务插画<ChevronRight size={16} /></summary>
        <div>
        {sections.map((section) => (
          <figure key={section.image}>
            <img src={section.image} alt={section.alt} loading="lazy" decoding="async" />
            <figcaption>
              <strong>{section.title}</strong>
            </figcaption>
          </figure>
        ))}
        </div>
      </details>
    </section>
  );
}
