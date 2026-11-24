// The project stepper reports each step's status from what the API (or this session) knows.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installFakeApi, json, mappingWith, renderApp, validRoles } from './test-utils';

const steps = async () => within(await screen.findByRole('navigation', { name: 'Project steps' }));

describe('project stepper status', () => {
  it('shows Uploaded for a project with data, To review for consent and To confirm for valid roles', async () => {
    installFakeApi();
    renderApp('/projects/demo/data');
    expect(await (await steps()).findByRole('link', { name: /Data.*Uploaded/ })).toBeInTheDocument();
    expect((await steps()).getByRole('link', { name: /What is shared.*To review/ })).toBeInTheDocument();
    expect(await (await steps()).findByRole('link', { name: /Column roles.*To confirm/ })).toBeInTheDocument();
  });

  it('counts roles to fix and shows Confirmed once the mapping is confirmed', async () => {
    const bad = validRoles.map((r) => (r.column === 'revenue' ? { ...r, ok: false, reason: 'No.' } : r));
    installFakeApi({ 'GET /api/projects/demo/mapping': () => json(200, mappingWith(bad)) });
    const view = renderApp('/projects/demo/data');
    expect(await (await steps()).findByRole('link', { name: /Column roles.*1 to fix/ })).toBeInTheDocument();
    view.unmount();

    installFakeApi({ 'GET /api/projects/demo/mapping': () => json(200, mappingWith(validRoles, 3, 'confirmed')) });
    renderApp('/projects/demo/data');
    expect(await (await steps()).findByRole('link', { name: /Column roles.*Confirmed/ })).toBeInTheDocument();
  });

  it('marks What is shared as Allowed after consent in this session, and keeps it across steps', async () => {
    const user = userEvent.setup();
    installFakeApi({
      'POST /api/projects/demo/consent': (call) => json(200, { ...(call.body as object), accepted_at: '2026-11-24T10:00:00Z' }),
    });
    renderApp('/projects/demo/consent');
    await user.click(await screen.findByRole('button', { name: /Allow sharing/ }));
    expect(await (await steps()).findByRole('link', { name: /What is shared.*Allowed/ })).toBeInTheDocument();
    await user.click((await steps()).getByRole('link', { name: /Data/ }));
    await user.click((await steps()).getByRole('link', { name: /What is shared/ }));
    expect(await screen.findByRole('button', { name: 'Allowed' })).toBeDisabled();
  });

  it('keeps the main action in a sticky bar on the consent and mapping steps', async () => {
    installFakeApi();
    renderApp('/projects/demo/mapping');
    const confirm = await screen.findByRole('button', { name: 'Confirm roles' });
    expect(confirm.closest('[data-slot="card-footer"]')).toHaveAttribute('data-sticky', 'true');
  });
});

describe('sidebar selection across project steps', () => {
  it('keeps the project selected in the sidebar on every step', async () => {
    installFakeApi();
    for (const step of ['data', 'consent', 'mapping']) {
      const view = renderApp(`/projects/demo/${step}`);
      const nav = await screen.findByRole('navigation', { name: 'Main' });
      expect(await within(nav).findByRole('link', { name: /Pet food, Germany/ }), step).toHaveAttribute('aria-current', 'page');
      view.unmount();
    }
  });
});

describe('project steps on a phone (below 768 px)', () => {
  const narrow = () =>
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  afterEach(() => vi.unstubAllGlobals());

  const region = async () => within(await screen.findByRole('region', { name: 'Project steps' }));

  it('stacks the steps and opens only the current one, with its screen below its header', async () => {
    narrow();
    installFakeApi();
    renderApp('/projects/demo/consent');
    const steps = await region();
    const open = steps.getByRole('button', { name: /What is shared/ });
    expect(open).toHaveAttribute('aria-expanded', 'true');
    expect(await steps.findByRole('button', { name: /Allow sharing/ })).toBeVisible();
    expect(steps.getByRole('link', { name: /Data/ })).toBeInTheDocument();
    expect(steps.getByRole('link', { name: /Column roles/ })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Project steps' })).toBeNull();
  });

  it('closes the open step when another one is opened, and folds the open one on its header', async () => {
    const user = userEvent.setup();
    narrow();
    installFakeApi();
    renderApp('/projects/demo/consent');
    await user.click((await region()).getByRole('link', { name: /Column roles/ }));
    const steps = await region();
    expect(await steps.findByRole('button', { name: /Column roles/ })).toHaveAttribute('aria-expanded', 'true');
    expect(steps.getByRole('link', { name: /What is shared/ })).toBeInTheDocument();
    expect(steps.queryByRole('button', { name: /Allow sharing/ })).toBeNull();

    const header = steps.getByRole('button', { name: /Column roles/ });
    await user.click(header);
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById('step-panel-mapping')).not.toBeVisible();
    await user.click(header);
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });
});
