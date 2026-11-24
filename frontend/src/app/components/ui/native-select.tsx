import { ChevronDown } from 'lucide-react';
import type * as React from 'react';

import { cn } from '@/app/lib/utils';

// A native <select> styled like the house input: keyboard and screen-reader behaviour for free.
function NativeSelect({ className, ...props }: React.ComponentProps<'select'>) {
  return (
    <div className="relative w-full">
      <select
        data-slot="native-select"
        className={cn(
          'h-9 w-full appearance-none rounded-lg border border-input bg-card pr-9 pl-3 type-body-md text-foreground disabled:cursor-not-allowed disabled:bg-muted aria-invalid:border-destructive',
          className,
        )}
        {...props}
      />
      <ChevronDown aria-hidden className="pointer-events-none absolute top-2.5 right-3 size-4 text-muted-foreground" />
    </div>
  );
}

export { NativeSelect };
