const TOKEN_HEADER = 'X-GEASS-Token';

export async function apiInfo(token: string): Promise<unknown> {
  const res = await fetch('/api/info', { headers: { [TOKEN_HEADER]: token } });
  if (!res.ok) {
    throw new Error(`连接失败（HTTP ${res.status}），请检查 Token`);
  }
  return res.json();
}

export async function stopAgent(token: string): Promise<void> {
  const res = await fetch('/api/agent/stop', {
    method: 'POST',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) {
    throw new Error(`停止失败（HTTP ${res.status}）`);
  }
}

export async function transcribe(token: string, blob: Blob): Promise<string> {
  const form = new FormData();
  form.append('file', blob, 'audio.webm');
  const res = await fetch('/api/transcribe', {
    method: 'POST',
    headers: { [TOKEN_HEADER]: token },
    body: form,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `转写失败（HTTP ${res.status}）`);
  }
  const json = (await res.json()) as { text: string };
  return json.text;
}
