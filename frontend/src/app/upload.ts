// Upload with progress through the generated client (A1, A3). fetch() cannot report upload
// progress, so the generated `intakeUploadData` call is given this fetch-compatible transport,
// which sends the very Request the client built (headers, bearer token, multipart body) with XHR.

import { intakeUploadData } from '@/client';
import type { DataVersion } from '@/client';

export type Progress = { loaded: number; total: number };

export function xhrFetch(onProgress: (p: Progress) => void, signal?: AbortSignal): typeof fetch {
  return async (input, init) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const body = await request.blob();
    return new Promise<Response>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(request.method, request.url);
      request.headers.forEach((value, name) => xhr.setRequestHeader(name, value));
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress({ loaded: e.loaded, total: e.total });
      };
      xhr.onload = () => {
        const headers = new Headers();
        for (const line of xhr.getAllResponseHeaders().trim().split(/[\r\n]+/)) {
          const at = line.indexOf(':');
          if (at > 0) headers.append(line.slice(0, at).trim(), line.slice(at + 1).trim());
        }
        const nullBody = xhr.status === 204 || xhr.status === 304;
        resolve(new Response(nullBody ? null : xhr.responseText, { status: xhr.status, headers }));
      };
      xhr.onerror = () => reject(new TypeError('Network request failed'));
      xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'));
      signal?.addEventListener('abort', () => xhr.abort(), { once: true });
      xhr.send(body);
    });
  };
}

export async function uploadData(
  projectId: string,
  file: File,
  onProgress: (p: Progress) => void,
  signal?: AbortSignal,
): Promise<DataVersion> {
  const { data } = await intakeUploadData({
    path: { project_id: projectId },
    body: { file },
    fetch: xhrFetch(onProgress, signal),
    throwOnError: true,
  });
  return data;
}
