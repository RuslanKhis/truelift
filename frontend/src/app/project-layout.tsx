// One project: the page header, a stepper for the screens G15 owns (with each step's status),
// the AI banners, then the step itself. The stage machine lives in the backend (D2); these links
// only move between screens, and the status only reports what the API (or this session) knows.
// From 768 px the steps are a horizontal stepper above the screen; below 768 px they are a vertical
// accordion: the current step's box holds its screen, and opening another step closes it.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { NavLink, Outlet, useLocation, useParams } from 'react-router';

import type { ConsentRecord } from '@/client';

import { aiStatusStore } from './ai-status';
import { AiBanner } from './components/ai-banner';
import { ErrorNotice } from './components/error-notice';
import { NavLabel } from './components/nav-label';
import { PageHeader } from './components/page-header';
import { cn } from './lib/utils';
import { keys, mappingQuery, projectQuery, usageQuery } from './queries';

export function useProjectId(): string {
  const { projectId } = useParams();
  if (!projectId) throw new Error('Route has no project ID');
  return projectId;
}

/** The consent recorded in this session, if any (no read route yet; see keys.consent). */
export function useSessionConsent(projectId: string): ConsentRecord | null {
  const queryClient = useQueryClient();
  const key = keys.consent(projectId);
  const { data } = useQuery({
    queryKey: key,
    // Never fetched: keep whatever this session wrote, also when the project's queries are invalidated.
    queryFn: () => queryClient.getQueryData<ConsentRecord | null>(key) ?? null,
    staleTime: Infinity,
  });
  return data ?? null;
}

type StepStatus = { done: boolean; caption: string };

function useStepStatuses(projectId: string): Record<'data' | 'consent' | 'mapping', StepStatus> {
  const project = useQuery(projectQuery(projectId));
  const mapping = useQuery(mappingQuery(projectId));
  const consent = useSessionConsent(projectId);
  const uploaded = project.data?.data_version != null;
  const invalid = mapping.data?.roles.filter((r) => !r.ok).length ?? 0;
  const confirmed = mapping.data?.status === 'confirmed';
  return {
    data: { done: uploaded, caption: uploaded ? 'Uploaded' : 'To do' },
    consent: { done: consent !== null, caption: consent ? 'Allowed' : 'To review' },
    mapping: {
      done: confirmed,
      caption: confirmed ? 'Confirmed' : invalid > 0 ? `${invalid} to fix` : 'To confirm',
    },
  };
}

const STEPS = [
  { to: 'data', label: 'Data' },
  { to: 'consent', label: 'What is shared' },
  { to: 'mapping', label: 'Column roles' },
] as const;

const WIDE = '(min-width: 48rem)';

/** True from 768 px. Without matchMedia (tests, old browsers) it assumes the wide layout. */
function useWide(): boolean {
  return useSyncExternalStore(
    (fn) => {
      if (typeof window.matchMedia !== 'function') return () => {};
      const mq = window.matchMedia(WIDE);
      mq.addEventListener('change', fn);
      return () => mq.removeEventListener('change', fn);
    },
    () => (typeof window.matchMedia === 'function' ? window.matchMedia(WIDE).matches : true),
    () => true,
  );
}

type Step = (typeof STEPS)[number];

/** The number (or tick) circle, the label and the status caption of one step. */
function StepMark({ step, index, status, active }: { step: Step; index: number; status: StepStatus; active: boolean }) {
  return (
    <>
      <span
        aria-hidden
        className={cn(
          'flex size-8 shrink-0 items-center justify-center rounded-full tabular-nums',
          active
            ? 'bg-primary type-label-primary text-primary-foreground'
            : status.done
              ? 'bg-accent type-label-md text-primary-ink'
              : 'border border-input bg-card type-label-md text-muted-foreground',
        )}
      >
        {status.done && !active ? <Check className="size-4" /> : index + 1}
      </span>
      <span className="flex min-w-0 flex-1 flex-col text-left">
        <span className={cn('type-body-md', active && 'font-semibold')}>
          <NavLabel>{step.label}</NavLabel>
        </span>
        <span className={cn('type-caption', status.done ? 'text-success' : 'text-muted-foreground')}>
          <span className="sr-only">, </span>
          {status.caption}
        </span>
      </span>
    </>
  );
}

function HorizontalSteps({ status }: { status: Record<Step['to'], StepStatus> }) {
  return (
    <nav aria-label="Project steps">
      <ol className="flex items-center gap-3">
        {STEPS.map((step, i) => {
          const s = status[step.to];
          return (
            <li key={step.to} className="flex items-center gap-3">
              {i > 0 ? <span aria-hidden className={cn('h-px w-8 md:w-14', s.done ? 'bg-primary-ink' : 'bg-border')} /> : null}
              <NavLink
                to={step.to}
                preventScrollReset
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-xl px-2 py-1.5 transition-[background-color,color] duration-150 ease-out',
                    isActive ? 'text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )
                }
              >
                {({ isActive }) => <StepMark step={step} index={i} status={s} active={isActive} />}
              </NavLink>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * Below 768 px: one header box per step, stacked. The current step is open, its screen right below
 * its header; the other headers are links, so opening one moves there and closes the current one.
 * The open header is a button that folds the screen away (and opens it again) without leaving it.
 * A labelled section, not a nav, because it holds the screen itself.
 */
function StepAccordion({ status }: { status: Record<Step['to'], StepStatus> }) {
  const { pathname } = useLocation();
  const current = STEPS.find((s) => pathname.endsWith(`/${s.to}`))?.to;
  const [folded, setFolded] = useState<{ path: string; folded: boolean }>({ path: pathname, folded: false });
  const isFolded = folded.path === pathname && folded.folded;
  const openHeader = useRef<HTMLButtonElement>(null);
  const shown = useRef(current);
  // After moving to another step, bring its header to the top of the screen (below the pinned links):
  // the box that closed above it may have pulled it far up or down. Not on first load.
  useEffect(() => {
    if (shown.current === current) return;
    shown.current = current;
    const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    openHeader.current?.scrollIntoView?.({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
  }, [current]);
  return (
    <section aria-label="Project steps">
      <ol className="flex flex-col gap-3">
        {STEPS.map((step, i) => {
          const s = status[step.to];
          const active = step.to === current;
          const header = cn(
            'flex w-full scroll-mt-20 items-center gap-3 rounded-xl border bg-card px-4 py-3 text-left shadow-card',
            active ? 'border-primary-ink' : 'border-border text-muted-foreground',
          );
          return (
            <li key={step.to} className="flex flex-col gap-4">
              {active ? (
                <button
                  ref={openHeader}
                  type="button"
                  aria-expanded={!isFolded}
                  aria-controls={`step-panel-${step.to}`}
                  aria-current="step"
                  onClick={() => setFolded({ path: pathname, folded: !isFolded })}
                  className={header}
                >
                  <StepMark step={step} index={i} status={s} active />
                  <ChevronDown
                    aria-hidden
                    className={cn('size-5 shrink-0 text-muted-foreground transition-[rotate] duration-200 ease-out', !isFolded && 'rotate-180')}
                  />
                </button>
              ) : (
                <NavLink to={step.to} preventScrollReset className={header}>
                  <StepMark step={step} index={i} status={s} active={false} />
                  <ChevronDown aria-hidden className="size-5 shrink-0 text-muted-foreground" />
                </NavLink>
              )}
              {active ? (
                <div id={`step-panel-${step.to}`} hidden={isFolded} className="pb-2">
                  <Outlet />
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function ProjectLayout() {
  const projectId = useProjectId();
  const project = useQuery(projectQuery(projectId));
  const usage = useQuery(usageQuery(projectId));
  const status = useStepStatuses(projectId);
  const wide = useWide();

  useEffect(() => {
    if (usage.data) aiStatusStore.applyUsage(usage.data.ai_state);
  }, [usage.data]);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <PageHeader
        eyebrow="Project"
        title={project.data?.name ?? projectId}
        lead="Upload your weekly sales, check what would be shared with your AI provider, then confirm what each column means."
      />
      {project.error ? <ErrorNotice error={project.error} title="This project could not be opened." /> : null}
      {/* Status comes from the API (data, mapping) or this session (consent); never a guessed tick. */}
      {wide ? (
        <>
          <HorizontalSteps status={status} />
          <AiBanner />
          <Outlet />
        </>
      ) : (
        <>
          <AiBanner />
          <StepAccordion status={status} />
        </>
      )}
    </div>
  );
}
