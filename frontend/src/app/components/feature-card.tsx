import type { LucideIcon } from 'lucide-react';

import { IconChip } from './icon-chip';

/** A landing card: optional step number, icon chip, title and one line. */
export function FeatureCard({
  icon: Icon,
  title,
  children,
  step,
}: {
  icon: LucideIcon;
  title: string;
  children: string;
  step?: number;
}) {
  return (
    <li className="flex flex-col gap-4 rounded-2xl border border-card-edge bg-card p-5 shadow-card transition-[translate,box-shadow] duration-200 ease-out hover:-translate-y-1 hover:shadow-card-hover motion-reduce:transition-none motion-reduce:hover:translate-y-0 md:p-6">
      <div className="flex items-center justify-between">
        <IconChip icon={Icon} />
        {step ? (
          <span className="type-metric text-border" aria-hidden>
            {String(step).padStart(2, '0')}
          </span>
        ) : null}
      </div>
      <div className="flex flex-col gap-1.5">
        <h3 className="type-title-md">
          {step ? <span className="sr-only">Step {step}: </span> : null}
          {title}
        </h3>
        <p className="text-muted-foreground">{children}</p>
      </div>
    </li>
  );
}
