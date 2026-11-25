// A6: the "AI unavailable" and "AI paused: budget reached" banners render from the stub stream's
// events, and the deterministic screens stay usable.
// A5: all server text renders as text (SB10).

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { aiStatusStore } from './ai-status';
import { readAgentEvents } from './stream';
import { disclosure, installFakeApi, json, profile, renderApp, usage, validRoles } from './test-utils';

const FIXTURES = resolve(import.meta.dirname, '../../../src/truelift/api/fixtures');

/** Replay a recorded fixture through the real reader into the store, as G16's chat will. */
async function replay(name: string) {
  const sse = readFileSync(resolve(FIXTURES, `agent_${name}.jsonl`), 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => {
      const e = JSON.parse(l) as { seq: number; type: string };
      return `id: ${e.seq}\nevent: ${e.type}\ndata: ${l.trim()}\n\n`;
    })
    .join('');
  await act(async () => {
    for await (const event of readAgentEvents(new Response(sse))) aiStatusStore.applyEvent(event);
  });
}

afterEach(() => aiStatusStore.reset());

describe('AI banners (A6; C15)', () => {
  it('shows "AI unavailable" from the ai_unavailable recording, and mapping stays usable', async () => {
    const user = userEvent.setup();
    const calls = installFakeApi({
      'POST /api/projects/demo/mapping/confirm': () =>
        json(200, { version: 1, status: 'confirmed', data_fingerprint: 'x', roles: validRoles }),
    });
    renderApp('/projects/demo/mapping');
    const confirm = await screen.findByRole('button', { name: 'Confirm roles' });
    expect(screen.queryByText('AI unavailable')).not.toBeInTheDocument();

    await replay('ai_unavailable');
    expect(screen.getByText('AI unavailable')).toBeInTheDocument();
    expect(screen.getByText(/the provider did not answer/)).toBeInTheDocument();

    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(await screen.findByText('Mapping confirmed')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST' && c.path.endsWith('/mapping/confirm'))).toBe(true);
  });

  it('shows "AI paused: budget reached" from the budget_paused recording, and upload stays usable', async () => {
    installFakeApi();
    renderApp('/projects/demo/data');
    await screen.findByLabelText('CSV file');
    await replay('budget_paused');
    expect(screen.getByText('AI paused: budget reached')).toBeInTheDocument();
    expect(screen.getByText('AI paused: budget reached. Raise it or continue without AI.')).toBeInTheDocument();
    expect(screen.getByLabelText('CSV file')).toBeEnabled();
  });

  it('shows the budget banner when the usage endpoint says so before any stream', async () => {
    installFakeApi({ 'GET /api/projects/demo/usage': () => json(200, { ...usage, ai_state: 'budget_paused' }) });
    renderApp('/projects/demo/data');
    expect(await screen.findByText('AI paused: budget reached')).toBeInTheDocument();
  });
});

describe('server text renders as text (A5; SB10)', () => {
  const HOSTILE = '<img src=x onerror="window.__pwned=1"><b>bold</b>';

  it('renders hostile strings from every screen as literal text', async () => {
    installFakeApi({
      'GET /api/projects': () => json(200, [{ id: 'demo', name: HOSTILE, stage: 'data', updated_at: '2026-11-05T10:00:00Z' }]),
      'GET /api/projects/demo/disclosure': () =>
        json(200, {
          ...disclosure,
          categories: [{ id: 'x', title: HOSTILE, description: HOSTILE }],
          example_payload: { note: HOSTILE },
          retention_note: HOSTILE,
        }),
      'POST /api/projects/demo/consent': () => json(409, { code: 'disclosure_changed', message: HOSTILE, request_id: 'r' }),
    });
    const { container } = renderApp('/projects/demo/consent');
    expect(await screen.findAllByText(HOSTILE)).not.toHaveLength(0);
    await userEvent.setup().click(screen.getByRole('button', { name: /Allow sharing/ }));
    expect(within(await screen.findByRole('alert')).getByText(HOSTILE)).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect((window as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it('renders hostile profile, mapping reasons and stream messages as text', async () => {
    installFakeApi({
      'GET /api/projects/demo/mapping': () =>
        json(200, {
          version: 1,
          status: 'proposed',
          data_fingerprint: 'x',
          roles: [{ column: HOSTILE, role: 'control', ok: false, reason: HOSTILE }],
        }),
      'GET /api/projects/demo/data/profile': () => json(200, { ...profile, observations: [HOSTILE] }),
    });
    const { container } = renderApp('/projects/demo/mapping');
    expect((await screen.findAllByText(HOSTILE)).length).toBeGreaterThanOrEqual(2);
    act(() =>
      aiStatusStore.applyEvent({ type: 'ai_status', seq: 2, turn_id: 't', state: 'unavailable', message: HOSTILE }),
    );
    expect(screen.getAllByText(HOSTILE).length).toBeGreaterThanOrEqual(3);
    expect(container.querySelector('img, b')).toBeNull();
  });
});
