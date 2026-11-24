// G15 against the real G02 stub API (A2, A3, A4, A6), through the app's own modules and the
// generated client. Node has no XMLHttpRequest, so the upload here uses the client's default
// fetch; the XHR progress transport is covered by src/app/upload.test.ts.

import { beforeAll, describe, expect, inject, it } from 'vitest';

import { aiStatusStore } from '@/app/ai-status';
import { configureApi } from '@/app/api';
import { ApiError, INTAKE_ERROR_CODES, INTAKE_REJECTIONS, isIntakeRejection } from '@/app/errors';
import { readAgentEvents, sendAgentMessage } from '@/app/stream';
import { rememberLaunchToken } from '@/app/token';
import {
  intakeConfirmMapping,
  intakeGetMapping,
  intakePutMapping,
  intakeUploadData,
  setupGetDisclosure,
  setupGetSetup,
  setupPostConsent,
  setupPutApiKey,
} from '@/client';
import { client } from '@/client/client.gen';

const PROJECT = 'petfood-de';

async function rejectionOf(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error('expected the request to be rejected');
}

const csv = (name: string, body = 'week,region,revenue\n2026-01-05,north,10\n') =>
  new File([body], name, { type: 'text/csv' });

beforeAll(() => {
  const url = inject('stubUrl');
  rememberLaunchToken(inject('stubToken'));
  configureApi();
  // Outside a browser the same-origin Origin header has to be set by hand (D12 Origin check).
  client.setConfig({ baseUrl: url, headers: { Origin: url } });
});

describe('A3 upload rejections from the stub contract', () => {
  it.each(INTAKE_ERROR_CODES)('%s is rejected with a plain-language reason the UI knows', async (code) => {
    const file = code === 'empty_file' ? csv(`${code}.csv`, '') : csv(`${code}.csv`);
    const error = await rejectionOf(
      intakeUploadData({ path: { project_id: PROJECT }, body: { file }, throwOnError: true }),
    );
    expect(error.status).toBe(422);
    expect(error.code).toBe(code);
    expect(isIntakeRejection(error.code)).toBe(true);
    expect(INTAKE_REJECTIONS[code].title.length).toBeGreaterThan(5);
    expect(error.message.length).toBeGreaterThan(5);
  });

  it('a non-CSV name is rejected as not_csv', async () => {
    const error = await rejectionOf(
      intakeUploadData({ path: { project_id: PROJECT }, body: { file: csv('sales.xlsx') }, throwOnError: true }),
    );
    expect(error.code).toBe('not_csv');
  });

  it('a weekly CSV is accepted and versioned', async () => {
    const { data } = await intakeUploadData({
      path: { project_id: PROJECT },
      body: { file: csv('sales_panel.csv') },
      throwOnError: true,
    });
    expect(data.filename).toBe('sales_panel.csv');
    expect(data.version).toBeGreaterThanOrEqual(2);
  });
});

describe('A2 setup, disclosure and consent', () => {
  it('lists providers and accepts a key without echoing it', async () => {
    const { data } = await setupGetSetup({ throwOnError: true });
    expect(data.providers.length).toBeGreaterThan(0);
    const put = await setupPutApiKey({
      body: { provider: 'claude', api_key: 'test-key-not-real-0000' },
      throwOnError: true,
    });
    expect(put.response.status).toBe(204);
    expect(await put.response.clone().text()).toBe('');
  });

  it('a too-short key is refused with field errors that do not echo it', async () => {
    const error = await rejectionOf(setupPutApiKey({ body: { provider: 'claude', api_key: 'short' }, throwOnError: true }));
    expect(error.status).toBe(422);
    expect(JSON.stringify(error.fields)).not.toContain('short"');
  });

  it('renders a disclosure with categories and an example payload, then records consent', async () => {
    const { data: disclosure } = await setupGetDisclosure({
      path: { project_id: PROJECT },
      query: { provider: 'gemini' },
      throwOnError: true,
    });
    expect(disclosure.categories.length).toBeGreaterThan(0);
    expect(Object.keys(disclosure.example_payload).length).toBeGreaterThan(0);
    const { data: record } = await setupPostConsent({
      path: { project_id: PROJECT },
      body: { provider: 'gemini', disclosure_version: disclosure.version },
      throwOnError: true,
    });
    expect(record.disclosure_version).toBe(disclosure.version);
    expect(record.provider).toBe('gemini');
  });

  it('a stale disclosure version is refused with disclosure_changed', async () => {
    const error = await rejectionOf(
      setupPostConsent({
        path: { project_id: PROJECT },
        body: { provider: 'gemini', disclosure_version: 'old-version' },
        throwOnError: true,
      }),
    );
    expect(error.status).toBe(409);
    expect(error.code).toBe('disclosure_changed');
  });
});

describe('A4 mapping validation from the stub', () => {
  it('reports a per-role reason, refuses to confirm while invalid, then confirms once fixed', async () => {
    const { data: start } = await intakeGetMapping({ path: { project_id: PROJECT }, throwOnError: true });
    const outcome = start.roles.find((r) => r.role === 'outcome');
    expect(outcome).toBeDefined();
    const roles = start.roles.map((r) => ({ column: r.column, role: r.role }));

    const broken = roles.map((r) => (r.column === outcome!.column ? { ...r, role: 'treatment_rate' as const } : r));
    const { data: invalid } = await intakePutMapping({
      path: { project_id: PROJECT },
      body: { expected_version: start.version, roles: broken },
      throwOnError: true,
    });
    const bad = invalid.roles.find((r) => r.column === outcome!.column);
    expect(bad?.ok).toBe(false);
    expect(bad?.reason).toBeTruthy();

    const refused = await rejectionOf(
      intakeConfirmMapping({ path: { project_id: PROJECT }, body: { version: invalid.version }, throwOnError: true }),
    );
    expect(refused.code).toBe('mapping_invalid');

    const { data: fixed } = await intakePutMapping({
      path: { project_id: PROJECT },
      body: { expected_version: invalid.version, roles },
      throwOnError: true,
    });
    expect(fixed.roles.every((r) => r.ok)).toBe(true);
    const { data: confirmed } = await intakeConfirmMapping({
      path: { project_id: PROJECT },
      body: { version: fixed.version },
      throwOnError: true,
    });
    expect(confirmed.status).toBe('confirmed');
  });

  it('a stale version is refused with stale_version', async () => {
    const error = await rejectionOf(
      intakeConfirmMapping({ path: { project_id: PROJECT }, body: { version: 1 }, throwOnError: true }),
    );
    expect(error.code).toBe('stale_version');
  });
});

describe('A6 AI banners from the stub stream', () => {
  it.each([
    ['ai_unavailable', 'unavailable'],
    ['budget_paused', 'budget_paused'],
  ] as const)('/scenario %s drives the AI state to %s', async (scenario, state) => {
    aiStatusStore.reset();
    const types: string[] = [];
    for await (const event of sendAgentMessage(PROJECT, `/scenario ${scenario}`)) {
      types.push(event.type);
      aiStatusStore.applyEvent(event);
    }
    expect(types[0]).toBe('turn_started');
    expect(types.at(-1)).toBe('turn_failed');
    expect(aiStatusStore.get().state).toBe(state);
    expect(aiStatusStore.get().message).toBeTruthy();
  });

  it('every event of the recorded interview validates against the runtime schema', async () => {
    const response = await fetch(`${inject('stubUrl')}/api/projects/${PROJECT}/agent/messages`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${inject('stubToken')}`,
        Origin: inject('stubUrl'),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text: 'hello' }),
    });
    expect(response.ok).toBe(true);
    const events = [];
    for await (const event of readAgentEvents(response)) events.push(event);
    expect(events.at(-1)?.type).toBe('turn_finished');
  });
});
