// A4: each column's role with the stub's per-role errors inline; Confirm stays disabled until
// every role is valid.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { RoleAssignment, RoleCheck } from '@/client';
import { installFakeApi, json, mappingWith, renderApp, validRoles } from '@/app/test-utils';

const REASON = 'A discount rate must be between 0 and 1 in every row.';
const invalidRoles: RoleCheck[] = validRoles.map((r) =>
  r.column === 'revenue' ? { column: 'revenue', role: 'treatment_rate', ok: false, reason: REASON } : r,
);

/** A tiny stand-in for the stub's check: revenue may not be a discount rate. */
function check(roles: RoleAssignment[]): RoleCheck[] {
  return roles.map((a) =>
    a.column === 'revenue' && a.role === 'treatment_rate'
      ? { ...a, ok: false, reason: REASON }
      : { ...a, ok: true, reason: null },
  );
}

describe('mapping review (A4)', () => {
  it('shows each role and its reason inline, with Confirm disabled while any role is invalid', async () => {
    installFakeApi({ 'GET /api/projects/demo/mapping': () => json(200, mappingWith(invalidRoles)) });
    renderApp('/projects/demo/mapping');

    const table = await screen.findByRole('region', { name: 'Column roles' });
    const revenue = within(table).getByLabelText('revenue');
    expect(revenue).toHaveValue('treatment_rate');
    expect(revenue).toHaveAttribute('aria-invalid', 'true');
    expect(revenue).toHaveAccessibleDescription(`Not valid: ${REASON}`);
    expect(within(table).getAllByText('Valid')).toHaveLength(4);
    expect(screen.getByText('1 role needs fixing before you can confirm.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm roles' })).toBeDisabled();
  });

  it('sends a changed role to the backend and enables Confirm once every role is valid', async () => {
    const user = userEvent.setup();
    let version = 1;
    const calls = installFakeApi({
      'GET /api/projects/demo/mapping': () => json(200, mappingWith(invalidRoles, version)),
      'PUT /api/projects/demo/mapping': (call) => {
        const body = call.body as { expected_version: number; roles: RoleAssignment[] };
        version = body.expected_version + 1;
        return json(200, mappingWith(check(body.roles), version));
      },
      'POST /api/projects/demo/mapping/confirm': (call) =>
        json(200, mappingWith(validRoles, (call.body as { version: number }).version, 'confirmed')),
    });
    renderApp('/projects/demo/mapping');

    await user.selectOptions(await screen.findByLabelText('revenue'), 'outcome');
    const confirm = screen.getByRole('button', { name: 'Confirm roles' });
    await waitFor(() => expect(confirm).toBeEnabled());

    const put = calls.find((c) => c.method === 'PUT');
    expect(put?.body).toMatchObject({ expected_version: 1 });
    expect((put?.body as { roles: RoleAssignment[] }).roles).toContainEqual({ column: 'revenue', role: 'outcome' });

    await user.click(confirm);
    expect(await screen.findByText('Mapping confirmed')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ version: 2 });
    expect(screen.getByRole('button', { name: 'Confirmed' })).toBeDisabled();
  });

  it('keeps Confirm disabled when a change makes a role invalid', async () => {
    const user = userEvent.setup();
    installFakeApi({
      'PUT /api/projects/demo/mapping': (call) => {
        const body = call.body as { expected_version: number; roles: RoleAssignment[] };
        return json(200, mappingWith(check(body.roles), body.expected_version + 1));
      },
    });
    renderApp('/projects/demo/mapping');
    const confirm = await screen.findByRole('button', { name: 'Confirm roles' });
    expect(confirm).toBeEnabled();
    await user.selectOptions(screen.getByLabelText('revenue'), 'treatment_rate');
    expect(await screen.findByText(REASON)).toBeInTheDocument();
    expect(confirm).toBeDisabled();
  });

  it('reloads after a stale version and says so', async () => {
    const user = userEvent.setup();
    const calls = installFakeApi({
      'PUT /api/projects/demo/mapping': () =>
        json(409, { code: 'stale_version', message: 'The mapping changed since you opened it. Reload and try again.', request_id: 'r' }),
    });
    renderApp('/projects/demo/mapping');
    await user.selectOptions(await screen.findByLabelText('revenue'), 'control');
    expect(await screen.findByText('The mapping changed since you opened it. Reload and try again.')).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.filter((c) => c.method === 'GET' && c.path.endsWith('/mapping')).length).toBeGreaterThanOrEqual(2),
    );
  });
});
