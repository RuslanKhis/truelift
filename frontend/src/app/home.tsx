// Landing: what truelift does at a glance (hero), how it works (on a slightly darker band), what
// you get, your projects, then a dark closing call to action and a one-line footer.
// Copy is plain and specific; there are no invented logos, testimonials or statistics.

import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  ChartPie,
  Check,
  CircleDollarSign,
  ClipboardCheck,
  FileUp,
  KeyRound,
  MessagesSquare,
  Ruler,
  ShieldCheck,
} from 'lucide-react';
import { Link } from 'react-router';

import { ErrorNotice } from './components/error-notice';
import { ExampleResult } from './components/example-result';
import { IconChip } from './components/icon-chip';
import { FeatureCard } from './components/feature-card';
import { Badge } from './components/ui/badge';
import { buttonVariants } from './components/ui/button';
import { cn } from './lib/utils';
import { projectsQuery } from './queries';

export const handle = { title: 'Home' };

const TRUST = ['Data stays on this computer', 'Your own AI key', 'Nothing is sent without your consent'];

function SectionTitle({ id, eyebrow, title, lead }: { id: string; eyebrow: string; title: string; lead: string }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-3 text-center">
      <p className="type-caption tracking-wide text-primary-ink uppercase">{eyebrow}</p>
      <h2 id={id} className="type-headline-lg">
        {title}
      </h2>
      <p className="type-lead text-muted-foreground">{lead}</p>
    </div>
  );
}

export function Component() {
  const projects = useQuery(projectsQuery());
  const first = projects.data?.[0];

  return (
    <div className="flex flex-col gap-20 pb-12 md:gap-28">
      <section aria-labelledby="hero-title" className="relative isolate -mx-4 -mt-6 px-4 pt-14 md:-mx-6 md:-mt-8 md:px-6 md:pt-20 xl:-mx-8 xl:px-8">
        <div aria-hidden className="bg-grid absolute inset-0 -z-10" />
        <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 text-center">
          <Badge variant="outline" className="bg-card">
            <ShieldCheck aria-hidden />
            Runs on your computer · your data stays local
          </Badge>
          <h2 id="hero-title" className="type-hero">
            Find out if your discounts <span className="text-primary-ink">actually pay off</span>.
          </h2>
          <p className="max-w-2xl type-lead text-muted-foreground">
            truelift interviews you about your market, maps what drives your sales and measures the true return on
            your discounts, with a range you can trust.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Link
              to={first ? `/projects/${first.id}/data` : '/setup'}
              className={cn(buttonVariants({ size: 'lg' }), 'gap-2')}
            >
              {first ? 'Open the demo project' : 'Get started'}
              <ArrowRight aria-hidden />
            </Link>
            <Link to="/setup" className={buttonVariants({ size: 'lg', variant: 'outline' })}>
              Set up your AI provider
            </Link>
          </div>
          <ul aria-label="Privacy" className="flex flex-col gap-2 text-muted-foreground sm:flex-row sm:flex-wrap sm:justify-center sm:gap-x-6">
            {TRUST.map((t) => (
              <li key={t} className="flex items-center justify-center gap-2 type-body-sm">
                <Check aria-hidden className="size-4 text-success" />
                {t}
              </li>
            ))}
          </ul>
        </div>
        <div className="mx-auto mt-12 w-full max-w-6xl md:mt-16">
          <ExampleResult />
        </div>
      </section>

      {/* Full-bleed band one step darker than the canvas, so the page has a rhythm without a gradient. */}
      <section
        aria-labelledby="how-title"
        className="-mx-4 border-y border-border bg-section px-4 py-16 md:-mx-6 md:px-6 md:py-20 xl:-mx-8 xl:px-8"
      >
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
          <SectionTitle
            id="how-title"
            eyebrow="How it works"
            title="From a spreadsheet to a measured answer"
            lead="Four steps, all on your computer. The AI asks the questions; the statistics give the answer."
          />
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FeatureCard step={1} icon={KeyRound} title="Connect your AI">
              Pick Gemini or Claude and add your own key. It stays on this computer.
            </FeatureCard>
            <FeatureCard step={2} icon={FileUp} title="Upload weekly sales">
              One row per week and region: sales, discounts and anything else you track.
            </FeatureCard>
            <FeatureCard step={3} icon={MessagesSquare} title="Answer a short interview">
              Explain how your market works. truelift drafts a cause-and-effect map you approve.
            </FeatureCard>
            <FeatureCard step={4} icon={CircleDollarSign} title="Get a measured return">
              A verdict on your discounts, with a range and a breakdown you can act on.
            </FeatureCard>
          </ol>
        </div>
      </section>

      <section aria-labelledby="get-title" className="mx-auto flex w-full max-w-6xl flex-col gap-10">
        <SectionTitle
          id="get-title"
          eyebrow="What you get"
          title="An answer you can defend in the next budget meeting"
          lead="Not a dashboard of guesses: one clear result, how sure it is, and where it holds."
        />
        <ul className="grid gap-4 md:grid-cols-3">
          <FeatureCard icon={ClipboardCheck} title="A clear verdict">
            Worth it, not worth it, or not yet clear, decided by a fixed rule, not by the AI.
          </FeatureCard>
          <FeatureCard icon={Ruler} title="Honest uncertainty">
            Every return comes with its 95% range, so you know how far to trust it.
          </FeatureCard>
          <FeatureCard icon={ChartPie} title="A breakdown you can act on">
            See where discounts pay and where they don't, by region and season.
          </FeatureCard>
        </ul>
      </section>

      <hr className="mx-auto w-full max-w-6xl border-t border-border" />

      <section aria-labelledby="projects-title" className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex items-end justify-between gap-4">
          <h2 id="projects-title" className="type-headline-lg">
            Your projects
          </h2>
          <Link to="/setup" className="type-label-md text-primary-ink hover:underline">
            AI provider settings
          </Link>
        </div>
        {projects.error ? <ErrorNotice error={projects.error} title="Projects could not be loaded." /> : null}
        {projects.data ? (
          <ul className="grid gap-4 md:grid-cols-2">
            {projects.data.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/projects/${p.id}/data`}
                  className="group flex items-center gap-4 rounded-xl border border-card-edge bg-card p-5 shadow-card transition-[border-color] duration-150 ease-out hover:border-primary-ink"
                >
                  <IconChip icon={ChartPie} />
                  <span className="flex flex-1 flex-col gap-1">
                    <span className="type-title-md">{p.name}</span>
                    <span className="type-body-sm text-muted-foreground">Stage: {p.stage.replace('_', ' ')}</span>
                  </span>
                  <ArrowRight aria-hidden className="size-5 text-muted-foreground group-hover:text-primary-ink" />
                </Link>
              </li>
            ))}
          </ul>
        ) : !projects.error ? (
          <p className="text-muted-foreground">Loading projects…</p>
        ) : null}
      </section>

      <section aria-labelledby="cta-title" className="mx-auto w-full max-w-6xl">
        {/* The focus ring turns gold here: the green ring would not show on the dark band. */}
        <div className="flex flex-col gap-8 rounded-2xl bg-band p-8 text-band-foreground [--ring:var(--gold)] md:p-12 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex max-w-2xl flex-col gap-3">
            <p className="type-caption tracking-wide text-gold uppercase">Ready when you are</p>
            <h2 id="cta-title" className="type-headline-lg">
              Start with one spreadsheet of weekly sales
            </h2>
            <p className="type-lead text-band-muted">
              Connect your AI, upload your data and get a measured return with its range. Nothing leaves this computer
              without your consent.
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-4 sm:flex-row sm:items-center">
            <Link
              to={first ? `/projects/${first.id}/data` : '/setup'}
              className={cn(buttonVariants({ size: 'lg', variant: 'gold' }), 'gap-2')}
            >
              {first ? 'Open the demo project' : 'Get started'}
              <ArrowRight aria-hidden />
            </Link>
            <Link to="/setup" className="type-label-md text-band-foreground underline underline-offset-4 hover:text-gold">
              Set up your AI provider
            </Link>
          </div>
        </div>
      </section>

      <footer className="mx-auto -mt-12 flex w-full max-w-6xl flex-col gap-1 type-caption text-muted-foreground sm:flex-row sm:justify-between md:-mt-20">
        <p>© 2026 the truelift authors · MIT licence</p>
        <p>Runs on this computer · your data stays local</p>
      </footer>
    </div>
  );
}
