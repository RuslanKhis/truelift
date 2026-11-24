// The agent stream (C15; contract in src/truelift/api/stream.py): POST, then Server-Sent Events
// read with fetch and the bearer header, never EventSource or a token in the URL (SB08). Every
// event is validated at run time with zod; a type assertion is not validation. G16 builds the
// chat on this reader; G15 uses its `ai_status` events for the AI banners (A6).

import { z } from 'zod';

import type { AgentEvent } from '@/client';

import { apiBaseUrl, authHeaders } from './api';
import { ApiError, toApiError } from './errors';

const aiState = z.enum(['available', 'no_key', 'consent_needed', 'unavailable', 'budget_paused']);
const base = { seq: z.number().int().min(1), turn_id: z.string() };

export const agentEventSchema = z.discriminatedUnion('type', [
  z.object({ ...base, type: z.literal('turn_started') }),
  z.object({ ...base, type: z.literal('text_delta'), message_id: z.string(), delta: z.string() }),
  z.object({ ...base, type: z.literal('text_done'), message_id: z.string(), text: z.string() }),
  z.object({ ...base, type: z.literal('tool_started'), call_id: z.string(), tool: z.string(), title: z.string() }),
  z.object({
    ...base,
    type: z.literal('tool_finished'),
    call_id: z.string(),
    tool: z.string(),
    ok: z.boolean(),
    summary: z.string(),
  }),
  // The proposal body is validated by G16, which renders it.
  z.object({ ...base, type: z.literal('proposal_created'), proposal: z.record(z.string(), z.unknown()) }),
  z.object({ ...base, type: z.literal('ai_status'), state: aiState, message: z.string() }),
  z.object({ ...base, type: z.literal('turn_finished') }),
  z.object({ ...base, type: z.literal('turn_failed'), code: z.string(), message: z.string() }),
]);

export type ValidatedAgentEvent = z.infer<typeof agentEventSchema>;

// Compile-time check that the runtime schema covers every generated event type.
type _Covers = AgentEvent['type'] extends ValidatedAgentEvent['type'] ? true : never;
const _covers: _Covers = true;
void _covers;

/** Split an SSE byte stream into the `data:` payload of each frame. */
export async function* sseData(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/g, '\n');
      let end: number;
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).replace(/^ /, ''))
          .join('\n');
        if (data) yield data;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export class StreamProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'StreamProtocolError';
  }
}

/** Parse and validate every event of a stream response; stop after the terminal event. */
export async function* readAgentEvents(response: Response): AsyncGenerator<ValidatedAgentEvent> {
  if (!response.body) throw new StreamProtocolError('The stream had no body.');
  let expected = 1;
  for await (const data of sseData(response.body)) {
    let json: unknown;
    try {
      json = JSON.parse(data);
    } catch {
      throw new StreamProtocolError('The assistant sent an unreadable event.');
    }
    const parsed = agentEventSchema.safeParse(json);
    if (!parsed.success) throw new StreamProtocolError('The assistant sent an event truelift does not understand.');
    if (parsed.data.seq !== expected) throw new StreamProtocolError('Events from the assistant arrived out of order.');
    expected += 1;
    yield parsed.data;
    if (parsed.data.type === 'turn_finished' || parsed.data.type === 'turn_failed') return;
  }
  throw new StreamProtocolError('The connection to the assistant ended before the turn finished.');
}

/** Send one message and yield its validated events. Abort with `signal` on Stop or unmount. */
export async function* sendAgentMessage(
  projectId: string,
  text: string,
  signal?: AbortSignal,
): AsyncGenerator<ValidatedAgentEvent> {
  let response: Response;
  const headers = authHeaders();
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'text/event-stream');
  try {
    response = await fetch(`${apiBaseUrl()}/api/projects/${encodeURIComponent(projectId)}/agent/messages`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw toApiError(error);
  }
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    throw toApiError(body, response);
  }
  yield* readAgentEvents(response);
}

export { ApiError };
