import { CircleCheck } from 'lucide-react';

import { Badge } from './ui/badge';

// The landing visual: what a truelift result looks like, built from the app's own pieces.
// The numbers are illustrative and the card says so; it is a picture of the product, not a record.
const RANGE = { low: 1.4, point: 2.1, high: 2.8 };
const SCALE = { min: 0, max: 3.5 };
const THRESHOLD = 1.0;
const REGIONS = [
  { name: 'North', roi: 2.6 },
  { name: 'Centre', roi: 2.0 },
  { name: 'South', roi: 1.2 },
];

const pct = (v: number) => `${((v - SCALE.min) / (SCALE.max - SCALE.min)) * 100}%`;

export function ExampleResult() {
  return (
    <figure className="w-full rounded-2xl border border-border bg-card p-5 text-left shadow-card md:p-8">
      <figcaption className="mb-5 flex flex-wrap items-center justify-between gap-2">
        <span className="type-label-md">Discount return, last 52 weeks</span>
        <Badge variant="outline">Example · illustrative numbers</Badge>
      </figcaption>
      <div className="grid gap-8 md:grid-cols-2 md:gap-12 lg:gap-16">
        <div className="flex flex-col gap-3">
          <Badge variant="success" className="self-start">
            <CircleCheck aria-hidden />
            Worth it
          </Badge>
          <p className="flex items-baseline gap-2">
            <span className="type-hero text-foreground">{RANGE.point.toFixed(1)}×</span>
            <span className="text-muted-foreground">return per euro of discount</span>
          </p>
          <div className="flex flex-col gap-2" role="img" aria-label="95% range from 1.4 to 2.8, above the break-even line at 1.0">
            <div className="relative h-3 rounded-full bg-muted">
              <span
                className="absolute inset-y-0 rounded-full bg-chart-1"
                style={{ left: pct(RANGE.low), width: `calc(${pct(RANGE.high)} - ${pct(RANGE.low)})` }}
              />
              <span className="absolute -inset-y-1.5 w-0.5 rounded-full bg-foreground" style={{ left: pct(THRESHOLD) }} />
            </div>
            <div className="flex justify-between type-caption text-muted-foreground">
              <span>Break-even {THRESHOLD.toFixed(1)}</span>
              <span className="tabular-nums">
                95% range {RANGE.low.toFixed(1)}–{RANGE.high.toFixed(1)}
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <p className="type-caption text-muted-foreground">By region</p>
          <ul className="flex flex-col gap-3">
            {REGIONS.map((r) => (
              <li key={r.name} className="grid grid-cols-[4.5rem_minmax(0,1fr)_2.5rem] items-center gap-3">
                <span className="type-body-sm">{r.name}</span>
                <span className="h-2.5 rounded-full bg-muted">
                  <span className="block h-full rounded-full bg-chart-1" style={{ width: pct(r.roi) }} />
                </span>
                <span className="text-right type-body-sm tabular-nums">{r.roi.toFixed(1)}×</span>
              </li>
            ))}
          </ul>
          <p className="type-body-sm text-muted-foreground">
            Every figure comes with the range it could really be in, and the assumptions behind it.
          </p>
        </div>
      </div>
    </figure>
  );
}
