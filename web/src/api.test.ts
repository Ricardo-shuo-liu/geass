import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiInfo, stopAgent, transcribe } from './api';

interface FetchResponse {
  ok: boolean;
  status: number;
  json?: () => Promise<unknown>;
  text?: () => Promise<string>;
}

function stubFetch(response: FetchResponse) {
  const fn = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) => response,
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api', () => {
  it('sends the token header with apiInfo', async () => {
    const fetchMock = stubFetch({ ok: true, status: 200, json: async () => ({ ok: true }) });

    const result = await apiInfo('tok-1');
    const [url, init] = fetchMock.mock.calls[0];

    expect(url).toBe('/api/info');
    expect(init?.headers).toEqual({ 'X-GEASS-Token': 'tok-1' });
    expect(result).toEqual({ ok: true });
  });

  it('throws the status message when apiInfo fails', async () => {
    stubFetch({ ok: false, status: 401, json: async () => ({}) });

    await expect(apiInfo('bad')).rejects.toThrow('连接失败（HTTP 401）');
  });

  it('stops the agent via POST', async () => {
    const fetchMock = stubFetch({ ok: true, status: 200 });

    await stopAgent('tok');
    const [url, init] = fetchMock.mock.calls[0];

    expect(url).toBe('/api/agent/stop');
    expect(init?.method).toBe('POST');
  });

  it('uploads a file form and returns the transcript', async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({ text: '你好' }),
    });

    const text = await transcribe('tok', new Blob(['audio']));
    const [, init] = fetchMock.mock.calls[0];
    const form = init?.body as FormData;

    expect(text).toBe('你好');
    expect(init?.method).toBe('POST');
    expect(form.get('file')).toBeInstanceOf(Blob);
  });

  it('surfaces the server error body from transcribe', async () => {
    stubFetch({ ok: false, status: 502, text: async () => '转写服务不可用' });

    await expect(transcribe('tok', new Blob())).rejects.toThrow('转写服务不可用');
  });
});
