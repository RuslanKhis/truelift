import type { LucideIcon } from 'lucide-react';

import { cn } from '@/app/lib/utils';

/**
 * The icon chip (DESIGN.md, Icon chips): a square pale gold chip with a two-tone icon, a deep green
 * stroke over a gold fill. Only use icons made of closed shapes; an open L-shaped path (an axis, a
 * zigzag line) fills into a stray triangle.
 */
export function IconChip({ icon: Icon, size = 'md' }: { icon: LucideIcon; size?: 'sm' | 'md' }) {
  return (
    <span
      aria-hidden
      className={cn(
        'flex shrink-0 items-center justify-center rounded-md bg-chip text-chip-foreground',
        size === 'md' ? 'size-12' : 'size-10',
      )}
    >
      <Icon className={cn('fill-chip-fill', size === 'md' ? 'size-6' : 'size-5')} strokeWidth={1.75} />
    </span>
  );
}
