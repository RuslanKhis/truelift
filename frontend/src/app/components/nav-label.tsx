// A navigation label that turns bold when selected without changing size or nudging its
// neighbours: an invisible bold copy reserves the wider width.
export function NavLabel({ children }: { children: string }) {
  return (
    <span className="inline-flex min-w-0 flex-col">
      <span className="truncate">{children}</span>
      <span aria-hidden className="invisible h-0 overflow-hidden font-semibold">
        {children}
      </span>
    </span>
  );
}
