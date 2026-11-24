// React Router in data mode. Every screen is lazy-loaded so no chunk passes Vite's size warning.

import { createBrowserRouter, isRouteErrorResponse, Navigate, useRouteError, type RouteObject } from 'react-router';

import { ProjectLayout } from './project-layout';
import { AppShell } from './shell';

function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? error.status === 404
      ? 'This page does not exist.'
      : error.statusText
    : 'Something went wrong on this screen. Reload the page to try again.';
  return (
    <div role="alert" className="flex flex-col gap-2 p-6">
      <h2 className="type-headline-md">This screen could not be shown</h2>
      <p className="text-muted-foreground">{message}</p>
    </div>
  );
}

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, lazy: () => import('./home') },
      { path: 'setup', lazy: () => import('@/routes/setup/provider') },
      {
        path: 'projects/:projectId',
        element: <ProjectLayout />,
        children: [
          { index: true, element: <Navigate to="data" replace /> },
          { path: 'data', lazy: () => import('@/routes/data/upload') },
          { path: 'consent', lazy: () => import('@/routes/setup/consent') },
          { path: 'mapping', lazy: () => import('@/routes/data/mapping') },
        ],
      },
      { path: '*', element: <RouteError /> },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}
