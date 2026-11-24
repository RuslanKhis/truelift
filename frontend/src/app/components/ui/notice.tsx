import { cva, type VariantProps } from 'class-variance-authority';
import type * as React from 'react';

import { cn } from '@/app/lib/utils';

// Unbordered notice on a *-subtle surface with an icon and words in the semantic colour
// (DESIGN.md: error after a partial answer, status surfaces). Fills, never borders.
const noticeVariants = cva('flex gap-3 rounded-xl px-4 py-3 type-body-md [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0', {
  variants: {
    variant: {
      info: 'bg-info-subtle text-foreground [&>svg]:text-info',
      warning: 'bg-warning-subtle text-foreground [&>svg]:text-warning',
      destructive: 'bg-destructive-subtle text-foreground [&>svg]:text-destructive',
      success: 'bg-success-subtle text-foreground [&>svg]:text-success',
    },
  },
  defaultVariants: { variant: 'info' },
});

type NoticeProps = React.ComponentProps<'div'> & VariantProps<typeof noticeVariants>;

function Notice({ className, variant, role = 'status', ...props }: NoticeProps) {
  return <div data-slot="notice" role={role} className={cn(noticeVariants({ variant }), className)} {...props} />;
}

function NoticeTitle({ className, ...props }: React.ComponentProps<'p'>) {
  return <p className={cn('type-label-md', className)} {...props} />;
}

function NoticeBody({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex min-w-0 flex-1 flex-col gap-1', className)} {...props} />;
}

export { Notice, NoticeBody, NoticeTitle };
