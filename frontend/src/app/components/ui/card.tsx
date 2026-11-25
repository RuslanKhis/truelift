import type { LucideIcon } from 'lucide-react';
import type * as React from 'react';

import { IconChip } from '@/app/components/icon-chip';
import { cn } from '@/app/lib/utils';

// Hairline border, 12 px radius (Tailwind rounded-xl in this mapping), 16-20 px padding, and the
// one resting elevation for cards (light mode only; dark mode uses the surface step).
function Card({ className, ...props }: React.ComponentProps<'section'>) {
  return (
    <section
      data-slot="card"
      className={cn(
        'flex flex-col gap-5 rounded-xl border border-border bg-card p-4 text-card-foreground shadow-card md:p-5',
        className,
      )}
      {...props}
    />
  );
}

/** A card header, optionally led by an icon chip (40 px, pale gold chip with a two-tone icon). */
function CardHeader({
  className,
  icon: Icon,
  children,
  ...props
}: React.ComponentProps<'div'> & { icon?: LucideIcon }) {
  if (!Icon) return <div data-slot="card-header" className={cn('flex flex-col gap-1', className)} {...props}>{children}</div>;
  return (
    <div data-slot="card-header" className={cn('flex items-start gap-3', className)} {...props}>
      <IconChip icon={Icon} size="sm" />
      <div className="flex min-w-0 flex-col gap-1">{children}</div>
    </div>
  );
}

function CardTitle({ className, ...props }: React.ComponentProps<'h2'>) {
  return <h2 data-slot="card-title" className={cn('type-title-md', className)} {...props} />;
}

function CardDescription({ className, ...props }: React.ComponentProps<'p'>) {
  return <p data-slot="card-description" className={cn('type-body-md text-muted-foreground', className)} {...props} />;
}

/**
 * The card's action row. `sticky` keeps it at the bottom of the viewport while the card is taller
 * than the screen, so the one action the step needs (Allow sharing, Confirm roles) stays in reach.
 */
function CardFooter({ className, sticky = false, ...props }: React.ComponentProps<'div'> & { sticky?: boolean }) {
  return (
    <div
      data-slot="card-footer"
      data-sticky={sticky || undefined}
      className={cn(
        'flex items-center justify-end gap-2',
        sticky &&
          'sticky bottom-0 z-10 -mx-4 -mb-4 rounded-b-xl border-t border-border bg-card px-4 py-3 md:-mx-5 md:-mb-5 md:px-5',
        className,
      )}
      {...props}
    />
  );
}

export { Card, CardDescription, CardFooter, CardHeader, CardTitle };
