import { cn } from '@/app/lib/utils';

// Determinate progress: a native <progress> for assistive technology, drawn with tokens.
function Progress({ value, max = 100, label, className }: { value: number; max?: number; label: string; className?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <div className="flex justify-between type-caption text-muted-foreground">
        <span>{label}</span>
        <span className="tabular-nums">{pct}%</span>
      </div>
      <progress
        aria-label={label}
        value={pct}
        max={100}
        className="h-1.5 w-full appearance-none overflow-hidden rounded-sm bg-muted [&::-moz-progress-bar]:bg-chart-1 [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-chart-1"
      />
    </div>
  );
}

export { Progress };
