import type { ReactNode } from 'react';

import { cn } from '@/app/lib/utils';

/** The top of every screen: a small eyebrow, the page title (display font) and one lead line. */
export function PageHeader({
  eyebrow,
  title,
  lead,
  actions,
  className,
}: {
  eyebrow: string;
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col gap-4 md:flex-row md:items-end md:justify-between', className)}>
      <div className="flex max-w-3xl flex-col gap-2">
        <p className="type-caption tracking-wide text-primary-ink uppercase">{eyebrow}</p>
        <h2 className="type-display">{title}</h2>
        {lead ? <p className="type-lead text-muted-foreground">{lead}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
    </div>
  );
}
