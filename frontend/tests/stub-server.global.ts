// Starts the real G02 stub API once for the `stub-api` test project and hands its URL and token
// to the tests. Needs uv (as `make check` does). Data goes to a temporary folder.

import { spawn, type ChildProcess } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import type { TestProject } from 'vitest/node';

declare module 'vitest' {
  export interface ProvidedContext {
    stubUrl: string;
    stubToken: string;
  }
}

function freePort(): Promise<number> {
  return new Promise((ok, fail) => {
    const srv = createServer();
    srv.unref();
    srv.on('error', fail);
    srv.listen(0, '127.0.0.1', () => {
      const address = srv.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      srv.close(() => ok(port));
    });
  });
}

async function waitForHealth(url: string, child: ChildProcess, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`stub server exited with code ${child.exitCode}`);
    try {
      const res = await fetch(`${url}/health`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error('stub server did not become healthy in time');
}

export default async function setup(project: TestProject) {
  const repo = resolve(import.meta.dirname, '..', '..');
  const port = await freePort();
  const token = randomBytes(32).toString('base64url');
  const dataDir = mkdtempSync(join(tmpdir(), 'truelift-g15-'));
  const child = spawn('uv', ['run', '--locked', 'python', 'frontend/tests/stub_server.py', String(port)], {
    cwd: repo,
    env: {
      ...process.env,
      TRUELIFT_TEST_TOKEN: token,
      TRUELIFT_PROJECTS_DIR: join(dataDir, 'projects'),
      TRUELIFT_STATE_DIR: join(dataDir, 'state'),
      TRUELIFT_DEV: '',
      VIRTUAL_ENV: '',
    },
    stdio: ['pipe', 'inherit', 'inherit'],
  });
  const url = `http://127.0.0.1:${port}`;
  try {
    await waitForHealth(url, child, 90_000);
  } catch (error) {
    child.stdin?.end();
    child.kill();
    throw error;
  }
  project.provide('stubUrl', url);
  project.provide('stubToken', token);

  return async () => {
    child.stdin?.end();
    await new Promise<void>((done) => {
      const timer = setTimeout(() => {
        child.kill();
        done();
      }, 5_000);
      child.once('exit', () => {
        clearTimeout(timer);
        done();
      });
    });
    rmSync(dataDir, { recursive: true, force: true });
  };
}
