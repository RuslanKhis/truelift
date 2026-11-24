// A2: choose a provider, send the key once (never kept in browser storage), see the disclosure
// with the example payload and record consent.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { disclosure, installFakeApi, json, renderApp } from '@/app/test-utils';

const KEY = 'test-key-not-real-0123456789';

describe('provider and key (A2)', () => {
  it('has a page title and explains why an AI model is needed and what it never does', async () => {
    installFakeApi();
    renderApp('/setup');
    expect(await screen.findByRole('heading', { level: 2, name: 'Connect an AI provider' })).toBeInTheDocument();
    const why = await screen.findByRole('region', { name: 'Why truelift needs an AI model' });
    expect(within(why).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Runs the interview',
      'Drafts the cause-and-effect map',
      'Explains the results in words',
    ]);
    expect(within(why).getByText(/calculated on this computer, never by the AI/)).toBeInTheDocument();
  });

  it('sends the key once for the chosen provider and keeps it nowhere in the browser', async () => {
    const user = userEvent.setup();
    const calls = installFakeApi({ 'PUT /api/setup/key': () => json(204) });
    const { queryClient } = renderApp('/setup');

    await user.click(await screen.findByRole('radio', { name: /Anthropic Claude/ }));
    const field = screen.getByLabelText('API key for Anthropic Claude');
    await user.type(field, KEY);
    await user.click(screen.getByRole('button', { name: 'Save key' }));

    expect(await screen.findByText(/The key for Anthropic Claude is saved/)).toBeInTheDocument();
    const puts = calls.filter((c) => c.method === 'PUT' && c.path === '/api/setup/key');
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({ provider: 'claude', api_key: KEY });

    expect(field).toHaveValue('');
    const everywhere = JSON.stringify({
      local: { ...window.localStorage },
      session: { ...window.sessionStorage },
      cache: queryClient.getQueryCache().getAll().map((q) => q.state.data),
      mutations: queryClient.getMutationCache().getAll().map((m) => m.state.data),
      url: window.location.href,
    });
    expect(everywhere).not.toContain(KEY);
  });

  it('shows a refused key in words and clears the field', async () => {
    const user = userEvent.setup();
    installFakeApi({
      'PUT /api/setup/key': () => json(422, { code: 'validation_error', message: 'Some fields are not valid.', request_id: 'r2' }),
    });
    renderApp('/setup');
    const field = await screen.findByLabelText('API key for Google Gemini');
    await user.type(field, KEY);
    await user.click(screen.getByRole('button', { name: 'Save key' }));
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('The key was not saved.')).toBeInTheDocument();
    expect(within(alert).getByText('Some fields are not valid.')).toBeInTheDocument();
    expect(field).toHaveValue('');
  });
});

describe('disclosure and consent (A2; C8, D17)', () => {
  it('renders the categories and the example payload, then records consent for that version', async () => {
    const user = userEvent.setup();
    const calls = installFakeApi({
      'POST /api/projects/demo/consent': (call) =>
        json(200, { ...(call.body as object), accepted_at: '2026-11-24T10:00:00Z' }),
    });
    renderApp('/projects/demo/consent');

    expect(await screen.findByText('Column names and types')).toBeInTheDocument();
    expect(screen.getByText('Up to 20 sample rows')).toBeInTheDocument();
    const payload = screen.getByRole('region', { name: /Example of what one request contains/ });
    expect(payload).toHaveTextContent('"revenue"');
    expect(payload).toHaveTextContent('"2026-01-05"');
    expect(screen.getByText(disclosure.retention_note)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Allow sharing with Google Gemini' }));
    expect(await screen.findByText('Sharing allowed')).toBeInTheDocument();
    const posts = calls.filter((c) => c.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual({ provider: 'gemini', disclosure_version: 'v-test-1' });
    expect(screen.getByRole('button', { name: 'Allowed' })).toBeDisabled();
  });

  it('asks for the disclosure of the provider the person picks', async () => {
    const user = userEvent.setup();
    const calls = installFakeApi();
    renderApp('/projects/demo/consent');
    await user.selectOptions(await screen.findByLabelText('Provider'), 'claude');
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/api/projects/demo/disclosure' && c.method === 'GET')).toBe(true),
    );
    expect(screen.getByRole('heading', { name: 'What truelift will share with Anthropic Claude' })).toBeInTheDocument();
  });

  it('a changed disclosure is reported and reloaded', async () => {
    const user = userEvent.setup();
    const calls = installFakeApi({
      'POST /api/projects/demo/consent': () =>
        json(409, { code: 'disclosure_changed', message: 'What will be shared has changed. Review it again.', request_id: 'r3' }),
    });
    renderApp('/projects/demo/consent');
    await user.click(await screen.findByRole('button', { name: /Allow sharing/ }));
    expect(await screen.findByText('What will be shared has changed. Review it again.')).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith('/disclosure')).length).toBeGreaterThanOrEqual(2));
  });
});
