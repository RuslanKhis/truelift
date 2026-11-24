// Test helpers for the screen tests (jsdom). The fake API answers like the G02 stub; the real stub
// is exercised by tests/stub-api.contract.test.ts. Demo data uses neutral column names.

import { QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { vi } from 'vitest';

import type { DataProfile, Disclosure, Mapping, RoleCheck, SetupStatus, Usage } from '@/client';

import { configureApi } from './api';
import { createQueryClient } from './queries';
import { routes } from './router';
import { rememberLaunchToken } from './token';

export const TOKEN = 'test-launch-token-0123456789abcdef';

export type Call = { method: string; path: string; headers: Headers; body: unknown };
type Handler = (call: Call) => { status: number; body?: unknown } | undefined;

export function json(status: number, body?: unknown) {
  return { status, body };
}

export const setupStatus: SetupStatus = {
  active_provider: 'gemini',
  providers: [
    { provider: 'gemini', label: 'Google Gemini', model_id: 'gemini-test', key_configured: true },
    { provider: 'claude', label: 'Anthropic Claude', model_id: 'claude-test', key_configured: false },
  ],
};

export const disclosure: Disclosure = {
  provider: 'gemini',
  version: 'v-test-1',
  categories: [
    { id: 'columns', title: 'Column names and types', description: 'The names and kinds of your columns.' },
    { id: 'sample_rows', title: 'Up to 20 sample rows', description: 'Never the whole file.' },
  ],
  example_payload: { columns: [{ name: 'revenue', type: 'money' }], sample_rows: [{ week: '2026-01-05' }] },
  retention_note: 'The provider keeps requests as its terms say.',
};

export const profile: DataProfile = {
  data_version: 2,
  rows: 520,
  weeks: 52,
  regions: 10,
  observations: ['Discounts were zero in some weeks.'],
  columns: [
    { name: 'week', semantic_type: 'date', min: null, max: null, missing_share: 0, ground_truth_excluded: false },
    { name: 'region', semantic_type: 'key', min: null, max: null, missing_share: 0, ground_truth_excluded: false },
    { name: 'revenue', semantic_type: 'money', min: 100, max: 9000, missing_share: 0, ground_truth_excluded: false },
    { name: 'discount_rate', semantic_type: 'rate', min: 0, max: 0.3, missing_share: 0, ground_truth_excluded: false },
    { name: 'answer_key', semantic_type: 'rate', min: 1, max: 4, missing_share: 0, ground_truth_excluded: true },
  ],
};

const ok = (column: string, role: RoleCheck['role']): RoleCheck => ({ column, role, ok: true, reason: null });

export function mappingWith(roles: RoleCheck[], version = 1, status: Mapping['status'] = 'proposed'): Mapping {
  return { version, status, data_fingerprint: 'sha256:test', roles };
}

export const validRoles: RoleCheck[] = [
  ok('week', 'date'),
  ok('region', 'region'),
  ok('revenue', 'outcome'),
  ok('discount_rate', 'treatment_rate'),
  ok('answer_key', 'ignore'),
];

export const usage: Usage = { tokens_used: 1000, token_budget: 2_000_000, ai_state: 'available' };

export function defaultHandlers(): Record<string, Handler> {
  return {
    'GET /api/projects': () =>
      json(200, [{ id: 'demo', name: 'Pet food, Germany', stage: 'data', updated_at: '2026-11-05T10:00:00Z' }]),
    'GET /api/projects/demo': () =>
      json(200, {
        id: 'demo',
        name: 'Pet food, Germany',
        stage: 'data',
        updated_at: '2026-11-05T10:00:00Z',
        data_version: 1,
        mapping_version: 1,
        dag_version: null,
        knowledge_version: 0,
      }),
    'GET /api/projects/demo/usage': () => json(200, usage),
    'GET /api/setup': () => json(200, setupStatus),
    'GET /api/projects/demo/disclosure': () => json(200, disclosure),
    'GET /api/projects/demo/data/profile': () => json(200, profile),
    'GET /api/projects/demo/mapping': () => json(200, mappingWith(validRoles)),
  };
}

/** Replace fetch with a router over `handlers`; returns the recorded calls. */
export function installFakeApi(overrides: Record<string, Handler> = {}): Call[] {
  const handlers = { ...defaultHandlers(), ...overrides };
  const calls: Call[] = [];
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    const text = request.method === 'GET' ? '' : await request.text();
    let body: unknown = text;
    try {
      body = text ? JSON.parse(text) : undefined;
    } catch {
      // not JSON
    }
    const call = { method: request.method, path: url.pathname, headers: request.headers, body };
    calls.push(call);
    const handler = handlers[`${request.method} ${url.pathname}`];
    const result = handler?.(call) ?? json(404, { code: 'not_found', message: 'Not found.', request_id: 'r-test' });
    const noBody = result.status === 204;
    return new Response(noBody ? null : JSON.stringify(result.body ?? {}), {
      status: result.status,
      headers: noBody ? {} : { 'Content-Type': 'application/json' },
    });
  });
  return calls;
}

export function renderApp(path: string, { token = TOKEN }: { token?: string | null } = {}) {
  if (token) rememberLaunchToken(token);
  configureApi();
  const queryClient = createQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...view, queryClient, router };
}
