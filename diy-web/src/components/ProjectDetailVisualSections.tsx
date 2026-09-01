import React from 'react';
import type { ProjectDetailVisualSection } from '../projectDetailVisuals';

export default function ProjectDetailVisualSections({ sections }: {
  sections: ProjectDetailVisualSection[];
}) {
  if (sections.length === 0) return null;

  return (
    <section className="project-detail-visuals" aria-label="项目体验介绍">
      <header>
        <span>招牌体验</span>
        <h2>这一程，会怎样慢慢放松</h2>
      </header>
      <div>
        {sections.map((section) => (
          <figure key={section.image}>
            <img src={section.image} alt={section.alt} loading="lazy" decoding="async" />
            <figcaption>
              <strong>{section.title}</strong>
              <p>{section.body}</p>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
