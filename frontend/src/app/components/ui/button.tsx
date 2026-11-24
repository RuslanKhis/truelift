import { cva, type VariantProps } from 'class-variance-authority';
import type * as React from 'react';

import { cn } from '@/app/lib/utils';

// shadcn base-nova button with the house rules applied (DESIGN.md, Components and Don'ts):
// hover primary-hover, press primary-active, no translate, no opacity hover, no dark: overrides,
// focus from the global 2 px outline, named transitions only. The primary label uses
// type-label-primary (heavier in dark mode, from the theme); every other variant type-label-md.
const buttonVariants = cva(
  'inline-flex shrink-0 items-center justify-center gap-2 rounded-lg whitespace-nowrap transition-[background-color,border-color,color] duration-150 ease-out disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:border-transparent [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  {
    variants: {
      variant: {
        default: 'bg-primary type-label-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active',
        outline: 'border border-input bg-card type-label-md text-foreground hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary type-label-md text-secondary-foreground hover:bg-accent hover:text-accent-foreground',
        ghost: 'type-label-md text-foreground hover:bg-accent hover:text-accent-foreground',
        destructive: 'bg-destructive type-label-md text-destructive-foreground',
        // The one action on the dark closing band: gold fill with the near-black brand label.
        gold: 'bg-gold type-label-md text-brand hover:bg-gold-hover active:bg-gold-hover',
        link: 'type-label-md text-primary-ink underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4',
        sm: 'h-8 px-3',
        lg: 'h-11 px-5',
        icon: 'size-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

type ButtonProps = React.ComponentProps<'button'> & VariantProps<typeof buttonVariants>;

function Button({ className, variant, size, type = 'button', ...props }: ButtonProps) {
  return <button data-slot="button" type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { Button, buttonVariants };
