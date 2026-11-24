// App shell (A1): a light sidebar (a step brighter than the canvas, with a hairline), a 48 px header
// holding the page h1 and the environment badge, and the work area. From 1024 px the sidebar is
// expanded (256 px); from 768 px it is an icon rail (72 px) so the work area keeps its room; below
// 768 px it is a top bar whose links stay pinned on scroll (the brand row scrolls away).
// Without a launch token (or after a 401) it shows how to reopen truelift instead.

import { useQuery } from '@tanstack/react-query';
import { FolderOpen, House, KeyRound, Moon, Sun, TrendingUp } from 'lucide-react';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { NavLink, Outlet, ScrollRestoration, useMatches } from 'react-router';

import { onUnauthorised } from './api';
import { NavLabel } from './components/nav-label';
import { Badge } from './components/ui/badge';
import { Button } from './components/ui/button';
import { cn } from './lib/utils';
import { projectsQuery } from './queries';
import { clearLaunchToken, getLaunchToken } from './token';

type Handle = { title?: string };

function usePageTitle(): string {
  const matches = useMatches();
  for (let i = matches.length - 1; i >= 0; i -= 1) {
    const title = (matches[i]?.handle as Handle | undefined)?.title;
    if (title) return title;
  }
  return 'truelift';
}

function readTheme(): 'dark' | 'light' {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

const themeListeners = new Set<() => void>();

function setTheme(theme: 'dark' | 'light'): void {
  const root = document.documentElement;
  // Suppress transitions for one frame while the theme class changes (DESIGN.md, Motion).
  root.style.setProperty('transition', 'none');
  root.classList.toggle('dark', theme === 'dark');
  try {
    window.localStorage.setItem('truelift-theme', theme);
  } catch {
    // Storage blocked: the choice lasts for this page only.
  }
  requestAnimationFrame(() => root.style.removeProperty('transition'));
  themeListeners.forEach((fn) => fn());
}

function ThemeToggle() {
  const theme = useSyncExternalStore(
    (fn) => {
      themeListeners.add(fn);
      return () => themeListeners.delete(fn);
    },
    readTheme,
    () => 'light' as const,
  );
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setTheme(next)}
      aria-label={`Use ${next} theme`}
      title={`Use ${next} theme`}
      className="text-sidebar-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:max-lg:w-full md:max-lg:px-0"
    >
      {theme === 'dark' ? <Sun aria-hidden /> : <Moon aria-hidden />}
      <span className="max-lg:sr-only">{theme === 'dark' ? 'Light theme' : 'Dark theme'}</span>
    </Button>
  );
}

const navItem = ({ isActive }: { isActive: boolean }) =>
  cn(
    'relative flex h-9 items-center gap-2 rounded-lg px-2.5 type-body-md md:max-lg:justify-center md:max-lg:px-0 text-sidebar-foreground transition-[background-color,color] duration-150 ease-out hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
    // Same size when selected; only the weight changes (NavLabel keeps the width steady), plus a
    // 2 px green marker on the left.
    isActive &&
      'bg-sidebar-accent font-semibold text-sidebar-accent-foreground before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-sidebar-primary',
  );

function ProjectLinks() {
  const projects = useQuery(projectsQuery());
  if (!projects.data?.length) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="px-2.5 pt-5 pb-1 type-caption text-sidebar-muted-foreground max-lg:hidden">Projects</p>
      <span aria-hidden className="mx-2 my-3 hidden h-px bg-sidebar-border md:max-lg:block" />
      {projects.data.map((p) => (
        // Points at the project, not one step, so it stays selected on Data, What is shared and Column roles.
        <NavLink key={p.id} to={`/projects/${p.id}`} className={navItem} title={p.name}>
          <FolderOpen aria-hidden className="size-4 shrink-0" />
          <span className="min-w-0 md:max-lg:sr-only">
            <NavLabel>{p.name}</NavLabel>
          </span>
        </NavLink>
      ))}
    </div>
  );
}

export function Relaunch() {
  return (
    <main className="mx-auto flex min-h-svh max-w-xl flex-col justify-center gap-4 px-4">
      <h1 className="type-headline-lg">Open truelift from its link</h1>
      <p className="text-muted-foreground">
        This page needs the link the <code className="type-code-sm">truelift</code> command printed when it started.
        Open that link, or run <code className="type-code-sm">uv run truelift</code> again for a new one.
      </p>
    </main>
  );
}

export function AppShell() {
  const [unauthorised, setUnauthorised] = useState(() => getLaunchToken() === null);
  const title = usePageTitle();

  useEffect(
    () =>
      onUnauthorised(() => {
        clearLaunchToken();
        setUnauthorised(true);
      }),
    [],
  );

  useEffect(() => {
    document.title = title === 'truelift' ? 'truelift' : `${title} · truelift`;
  }, [title]);

  if (unauthorised) return <Relaunch />;

  return (
    <div className="flex min-h-svh flex-col md:flex-row">
      <nav
        aria-label="Main"
        // Below 768 px the top bar is sticky with a negative offset the height of the brand row
        // (12 px padding + 40 px row), so the brand and theme switch scroll away and the links stay.
        className="sidebar-scope flex shrink-0 flex-col gap-1 border-sidebar-border bg-sidebar p-3 text-sidebar-foreground max-md:sticky max-md:-top-13 max-md:z-20 max-md:border-b md:sticky md:top-0 md:h-svh md:w-[72px] md:border-r lg:w-64"
      >
        <div className="flex items-center justify-between gap-2 px-1 py-1 md:pb-3 md:max-lg:justify-center md:max-lg:px-0">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="flex size-8 items-center justify-center rounded-lg bg-brand text-gold ring-1 ring-sidebar-border"
            >
              <TrendingUp className="size-4" strokeWidth={2.25} />
            </span>
            <span className="flex flex-col md:max-lg:sr-only">
              <span className="font-display text-[15px] leading-5 font-semibold">truelift</span>
              <span className="type-caption text-sidebar-muted-foreground max-md:hidden">Discount ROI, measured</span>
            </span>
          </div>
          <div className="md:hidden">
            <ThemeToggle />
          </div>
        </div>
        <div className="flex flex-col gap-1 max-md:flex-row max-md:flex-wrap">
          <NavLink to="/" end className={navItem} title="Home">
            <House aria-hidden className="size-4 shrink-0" />
            <span className="min-w-0 md:max-lg:sr-only">
              <NavLabel>Home</NavLabel>
            </span>
          </NavLink>
          <NavLink to="/setup" className={navItem} title="AI provider">
            <KeyRound aria-hidden className="size-4 shrink-0" />
            <span className="min-w-0 md:max-lg:sr-only">
              <NavLabel>AI provider</NavLabel>
            </span>
          </NavLink>
          <ProjectLinks />
        </div>
        <div className="mt-auto max-md:hidden">
          <ThemeToggle />
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4 md:px-6">
          <h1 className="truncate type-label-md">{title}</h1>
          <Badge variant="info" className="ml-auto">
            <span className="sr-only">Environment: </span>On this computer
          </Badge>
        </header>
        {/* Full width; each screen centres its own column (landing max-w-6xl, app screens max-w-5xl). */}
        <main className="w-full flex-1 px-4 py-6 md:px-6 md:py-8 xl:px-8">
          <Outlet />
        </main>
        {/* A new page opens at the top; back and forward restore where you were. Step links opt out. */}
        <ScrollRestoration />
      </div>
    </div>
  );
}
