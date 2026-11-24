import type { ReactNode } from 'react';

// A figure shown as a figure: caption label above a large tabular number in the display font.
export function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl bg-muted px-4 py-3">
      <dt className="type-caption text-muted-foreground">{label}</dt>
      <dd className="type-metric text-foreground">{value}</dd>
    </div>
  );
}

export function StatTiles({ children, label }: { children: ReactNode; label: string }) {
  return (
    <dl aria-label={label} className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {children}
    </dl>
  );
}
