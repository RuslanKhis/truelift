// A3: upload shows progress, and every rejection reason in the stub's error contract appears in
// plain language. XHR is faked here; tests/stub-api.contract.test.ts uploads to the real stub.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { INTAKE_ERROR_CODES, INTAKE_REJECTIONS } from '@/app/errors';
import { installFakeApi, renderApp, TOKEN } from '@/app/test-utils';

type Reply = { status: number; body: unknown };

class FakeXhr {
  static reply: Reply = { status: 201, body: {} };
  static sent: FakeXhr[] = [];
  static hold = false;
  method = '';
  url = '';
  headers: Record<string, string> = {};
  status = 0;
  responseText = '';
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name.toLowerCase()] = value;
  }
  getAllResponseHeaders() {
    return 'content-type: application/json\r\n';
  }
  send() {
    FakeXhr.sent.push(this);
    this.upload.onprogress?.({ lengthComputable: true, loaded: 40, total: 100 });
    if (!FakeXhr.hold) this.finish();
  }
  finish() {
    this.status = FakeXhr.reply.status;
    this.responseText = JSON.stringify(FakeXhr.reply.body);
    this.onload?.();
  }
  abort() {
    this.onabort?.();
  }
}

const accepted = {
  version: 2,
  filename: 'sales.csv',
  fingerprint: 'sha256:abc',
  rows: 520,
  columns: 5,
  uploaded_at: '2026-11-24T10:00:00Z',
};

beforeEach(() => {
  FakeXhr.sent = [];
  FakeXhr.hold = false;
  FakeXhr.reply = { status: 201, body: accepted };
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
});

async function chooseAndUpload(name = 'sales.csv') {
  const user = userEvent.setup();
  await user.upload(await screen.findByLabelText('CSV file'), new File(['week,region\n'], name, { type: 'text/csv' }));
  await user.click(screen.getByRole('button', { name: 'Upload' }));
  return user;
}

describe('upload (A3)', () => {
  it('shows progress while the file is sent through the generated client', async () => {
    installFakeApi();
    FakeXhr.hold = true;
    renderApp('/projects/demo/data');
    await chooseAndUpload();
    const bar = await screen.findByRole('progressbar', { name: 'Uploading' });
    expect(bar).toHaveAttribute('value', '40');
    const xhr = FakeXhr.sent[0]!;
    expect(xhr.method).toBe('POST');
    expect(new URL(xhr.url).pathname).toBe('/api/projects/demo/data');
    expect(xhr.headers['authorization']).toBe(`Bearer ${TOKEN}`);
    xhr.finish();
    expect(await screen.findByText('Uploaded sales.csv')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('shows the data profile after an accepted upload', async () => {
    installFakeApi();
    renderApp('/projects/demo/data');
    await chooseAndUpload();
    const table = await screen.findByRole('region', { name: 'Column profile' });
    expect(within(table).getByText('discount_rate')).toBeInTheDocument();
    expect(within(table).getByText('ground truth: excluded')).toBeInTheDocument();
    // The counts are stat tiles (label over figure), not a sentence.
    const summary = screen.getByLabelText('Data summary');
    expect(within(summary).getAllByRole('term').map((t) => t.textContent)).toEqual(['Rows', 'Weeks', 'Regions']);
    expect(within(summary).getAllByRole('definition').map((d) => d.textContent)).toEqual(['520', '52', '10']);
  });

  it.each(INTAKE_ERROR_CODES)('explains the %s rejection in plain language', async (code) => {
    installFakeApi();
    FakeXhr.reply = { status: 422, body: { code, message: 'server wording', request_id: 'r-up' } };
    renderApp('/projects/demo/data');
    await chooseAndUpload(`${code}.csv`);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(INTAKE_REJECTIONS[code].title);
    expect(alert).toHaveTextContent(INTAKE_REJECTIONS[code].hint);
  });

  it('explains a file that is too large (413)', async () => {
    installFakeApi();
    FakeXhr.reply = { status: 413, body: { code: 'payload_too_large', message: 'The request is too large.', request_id: 'r' } };
    renderApp('/projects/demo/data');
    await chooseAndUpload();
    expect(await screen.findByRole('alert')).toHaveTextContent(INTAKE_REJECTIONS.payload_too_large.title);
  });

  it('falls back to the server message for an unknown code', async () => {
    installFakeApi();
    FakeXhr.reply = { status: 422, body: { code: 'new_reason', message: 'A reason G07 added later.', request_id: 'r9' } };
    renderApp('/projects/demo/data');
    await chooseAndUpload();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('A reason G07 added later.');
    expect(alert).toHaveTextContent('Request ID: r9');
  });
});
