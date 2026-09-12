import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  addMcpServer,
  apiInfo,
  deleteMcpServer,
  detectSensitiveRegions,
  getPrivacyMasks,
  getTrust,
  pairDevice,
  setMcpToolEnabled,
  stopAgent,
  testMcpServer,
  transcribe,
  updateTrust,
} from './api';

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

  it('exchanges a pairing code for a token', async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({ token: 'tok-2' }),
    });

    const token = await pairDevice('pair-code');
    const [url, init] = fetchMock.mock.calls[0];

    expect(url).toBe('/api/pair');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ code: 'pair-code' });
    expect(token).toBe('tok-2');
  });

  it('surfaces pairing errors from the server', async () => {
    stubFetch({
      ok: false,
      status: 410,
      json: async () => ({ detail: '配对码已过期' }),
    });

    await expect(pairDevice('expired')).rejects.toThrow('配对码已过期');
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

  it('adds an MCP server with a JSON body', async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({ record: { verified: true } }),
    });

    await addMcpServer('tok', {
      name: 'demo',
      transport: 'stdio',
      command: 'echo',
      env: { TOKEN: 'secret' },
    });
    const [url, init] = fetchMock.mock.calls[0];

    expect(url).toBe('/api/resources/mcp');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      name: 'demo',
      transport: 'stdio',
      command: 'echo',
      env: { TOKEN: 'secret' },
    });
  });

  it('tests, toggles and deletes an MCP server', async () => {
    const fetchMock = stubFetch({ ok: true, status: 200, json: async () => ({ ok: true }) });

    await testMcpServer('tok', 'demo');
    await setMcpToolEnabled('tok', 'demo', 'add', false);
    await deleteMcpServer('tok', 'demo');

    const urls = fetchMock.mock.calls.map((call) => call[0]);
    expect(urls[0]).toBe('/api/resources/mcp/demo/test');
    expect(urls[1]).toBe('/api/resources/mcp/demo/tools/add/enabled');
    expect(urls[2]).toBe('/api/resources/mcp/demo');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST');
    expect(fetchMock.mock.calls[2][1]?.method).toBe('DELETE');
  });

  it('surfaces MCP detail errors from the server', async () => {
    stubFetch({
      ok: false,
      status: 409,
      json: async () => ({ detail: '服务器未通过测试，不能启用' }),
    });

    await expect(testMcpServer('tok', 'broken')).rejects.toThrow(
      '服务器未通过测试，不能启用',
    );
  });

  it('reads and updates trust settings', async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({
        mode: 'smart',
        visual_delay_ms: 600,
        overrides: {},
        task_allow_all: false,
      }),
    });

    await getTrust('tok');
    await updateTrust('tok', { mode: 'confirm' });

    expect(fetchMock.mock.calls[0][0]).toBe('/api/trust');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/trust');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST');
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      mode: 'confirm',
    });
  });

  it('reads privacy masks', async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({ enabled: false, masks: [] }),
    });

    const snapshot = await getPrivacyMasks('tok');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/privacy/masks');
    expect(snapshot).toEqual({ enabled: false, masks: [] });
  });

  it('requests sensitive region detection', async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({
        regions: [],
        sources: { password_fields: 0, keyword_matches: 0 },
        keywords: ['密码'],
      }),
    });

    const result = await detectSensitiveRegions('tok');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/privacy/detect');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
    expect(result.keywords).toEqual(['密码']);
  });
});
