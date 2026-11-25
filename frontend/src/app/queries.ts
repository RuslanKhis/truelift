// TanStack Query over the generated client (A1). One key factory; every call goes through the
// generated SDK, configured once in api.ts.

import { QueryClient, queryOptions } from '@tanstack/react-query';

import {
  intakeGetMapping,
  intakeGetProfile,
  projectsGetProject,
  projectsListProjects,
  setupGetDisclosure,
  setupGetSetup,
  setupGetUsage,
} from '@/client';
import type { Provider } from '@/client';

import type { ApiError } from './errors';

declare module '@tanstack/react-query' {
  interface Register {
    defaultError: ApiError;
  }
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Never retry a client error: it will not change on its own.
        retry: (count, error) => error.status >= 500 && count < 2,
      },
      mutations: { retry: false },
    },
  });
}

export const keys = {
  projects: ['projects'] as const,
  project: (id: string) => ['project', id] as const,
  setup: ['setup'] as const,
  disclosure: (id: string, provider: Provider) => ['project', id, 'disclosure', provider] as const,
  usage: (id: string) => ['project', id, 'usage'] as const,
  profile: (id: string) => ['project', id, 'profile'] as const,
  mapping: (id: string) => ['project', id, 'mapping'] as const,
  /** Consent recorded in this session. The API has no read route for consent yet (G11), so this
   *  cache entry is the only source; after a reload the step honestly shows "To review". */
  consent: (id: string) => ['project', id, 'consent'] as const,
};

export const projectsQuery = () =>
  queryOptions({ queryKey: keys.projects, queryFn: async () => (await projectsListProjects({ throwOnError: true })).data });

export const projectQuery = (id: string) =>
  queryOptions({
    queryKey: keys.project(id),
    queryFn: async () => (await projectsGetProject({ path: { project_id: id }, throwOnError: true })).data,
  });

export const setupQuery = () =>
  queryOptions({ queryKey: keys.setup, queryFn: async () => (await setupGetSetup({ throwOnError: true })).data });

export const disclosureQuery = (id: string, provider: Provider) =>
  queryOptions({
    queryKey: keys.disclosure(id, provider),
    queryFn: async () => (await setupGetDisclosure({ path: { project_id: id }, query: { provider }, throwOnError: true })).data,
  });

export const usageQuery = (id: string) =>
  queryOptions({
    queryKey: keys.usage(id),
    queryFn: async () => (await setupGetUsage({ path: { project_id: id }, throwOnError: true })).data,
  });

export const profileQuery = (id: string) =>
  queryOptions({
    queryKey: keys.profile(id),
    queryFn: async () => (await intakeGetProfile({ path: { project_id: id }, throwOnError: true })).data,
  });

export const mappingQuery = (id: string) =>
  queryOptions({
    queryKey: keys.mapping(id),
    queryFn: async () => (await intakeGetMapping({ path: { project_id: id }, throwOnError: true })).data,
  });
