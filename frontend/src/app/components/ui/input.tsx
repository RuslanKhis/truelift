import type * as React from 'react';

import { cn } from '@/app/lib/utils';

// Card fill, input edge, 8 px radius, 36 px tall; the error state adds a destructive edge.
function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'h-9 w-full min-w-0 rounded-lg border border-input bg-card px-3 type-body-md text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:bg-muted aria-invalid:border-destructive',
        className,
      )}
      {...props}
    />
  );
}

export { Input };
