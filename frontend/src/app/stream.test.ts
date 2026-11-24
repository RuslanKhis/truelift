// The stream reader against the repository's own recorded event files (the G02 fixtures the stub
// replays), framed exactly as src/truelift/api/stream.py frames them.

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { readAgentEvents, StreamProtocolError, type ValidatedAgentEvent } from './stream';

const FIXTURES = resolve(import.meta.dirname, '../../../src/truelift/api/fixtures');

function frames(events: object[]): string {
  return events
    .map((e) => {
      const ev = e as { seq: number; type: string };
      return `id: ${ev.seq}\nevent: ${ev.type}\ndata: ${JSON.stringify(e)}\n\n`;
    })
    .join('');
}

function recording(name: string): object[] {
  return readFileSync(resolve(FIXTURES, `agent_${name}.jsonl`), 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as object);
}

/** A Response whose body arrives in small chunks, splitting frames mid-way. */
function chunked(text: string, size = 7): Response {
  const bytes = new TextEncoder().encode(text);
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += size) controller.enqueue(bytes.slice(i, i + size));
      controller.close();
    },
  });
  return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
}

async function collect(response: Response): Promise<ValidatedAgentEvent[]> {
  const out: ValidatedAgentEvent[] = [];
  for await (const event of readAgentEvents(response)) out.push(event);
  return out;
}

describe('agent stream reader (C15)', () => {
  it.each(['interview', 'ai_unavailable', 'budget_paused', 'turn_failed'])(
    'validates every event of the %s recording',
    async (name) => {
      const events = recording(name);
      const parsed = await collect(chunked(frames(events)));
      expect(parsed).toHaveLength(events.length);
      expect(parsed[0]?.type).toBe('turn_started');
      expect(['turn_finished', 'turn_failed']).toContain(parsed.at(-1)?.type);
    },
  );

  it('rejects an event that does not match the contract', async () => {
    const bad = frames([{ seq: 1, turn_id: 't', type: 'turn_started' }, { seq: 2, turn_id: 't', type: 'ai_status', state: 'on_fire' }]);
    await expect(collect(chunked(bad))).rejects.toBeInstanceOf(StreamProtocolError);
  });

  it('rejects events out of order', async () => {
    const bad = frames([{ seq: 2, turn_id: 't', type: 'turn_started' }]);
    await expect(collect(chunked(bad))).rejects.toThrow(/out of order/);
  });

  it('reports a stream that ends before its terminal event', async () => {
    const cut = frames(recording('interview').slice(0, 3));
    await expect(collect(chunked(cut))).rejects.toThrow(/ended before the turn finished/);
  });
});
