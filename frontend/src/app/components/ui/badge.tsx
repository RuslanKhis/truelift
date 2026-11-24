import { cva, type VariantProps } from 'class-variance-authority';
import type * as React from 'react';

import { cn } from '@/app/lib/utils';

// Pill shape, caption type; status badges use the *-subtle fill with the semantic colour as text
// and always carry a word, never colour alone.
const badgeVariants = cva('inline-flex h-6 items-center gap-1 rounded-full px-2.5 type-caption whitespace-nowrap [&_svg]:size-3.5', {
  variants: {
    variant: {
      secondary: 'bg-secondary text-secondary-foreground',
      outline: 'border border-border text-foreground',
      success: 'bg-success-subtle text-success',
      warning: 'bg-warning-subtle text-warning',
      destructive: 'bg-destructive-subtle text-destructive',
      info: 'bg-info-subtle text-info',
    },
  },
  defaultVariants: { variant: 'secondary' },
});

function Badge({ className, variant, ...props }: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge };
