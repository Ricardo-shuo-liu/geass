const TOKEN_HEADER = 'X-GEASS-Token';

import type { ResourceSummary } from './types';

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

export async function getResources(token: string): Promise<ResourceSummary> {
  const res = await fetch('/api/resources', {
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) {
    throw new Error(`读取资源失败（HTTP ${res.status}）`);
  }
  return (await res.json()) as ResourceSummary;
}

export async function deleteMemoryEntry(token: string, key: string): Promise<void> {
  const res = await fetch(`/api/resources/memory/${encodeURIComponent(key)}`, {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`删除记忆失败（HTTP ${res.status}）`);
}

export async function clearMemory(token: string): Promise<void> {
  const res = await fetch('/api/resources/memory', {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`清空记忆失败（HTTP ${res.status}）`);
}

export async function addRagSource(
  token: string,
  path: string,
  name?: string,
  extensions?: string,
): Promise<void> {
  const res = await fetch('/api/resources/rag', {
    method: 'POST',
    headers: {
      [TOKEN_HEADER]: token,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ path, name, extensions }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `添加 RAG 数据源失败（HTTP ${res.status}）`);
  }
}

export async function removeRagSource(
  token: string,
  source: string,
): Promise<void> {
  const res = await fetch(`/api/resources/rag/${encodeURIComponent(source)}`, {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`删除数据源失败（HTTP ${res.status}）`);
}

export async function setRagEnabled(
  token: string,
  source: string,
  enabled: boolean,
): Promise<void> {
  const res = await fetch(
    `/api/resources/rag/${encodeURIComponent(source)}/enabled`,
    {
      method: 'POST',
      headers: {
        [TOKEN_HEADER]: token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ enabled }),
    },
  );
  if (!res.ok) throw new Error(`切换数据源失败（HTTP ${res.status}）`);
}

export async function reindexRag(
  token: string,
  source: string,
): Promise<void> {
  const res = await fetch(
    `/api/resources/rag/${encodeURIComponent(source)}/reindex`,
    {
      method: 'POST',
      headers: { [TOKEN_HEADER]: token },
    },
  );
  if (!res.ok) throw new Error(`重建索引失败（HTTP ${res.status}）`);
}

export async function deleteSkill(
  token: string,
  name: string,
): Promise<void> {
  const res = await fetch(`/api/resources/skills/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`删除技能失败（HTTP ${res.status}）`);
}

export async function deleteRot(token: string, name: string): Promise<void> {
  const res = await fetch(`/api/resources/pot/rot/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`删除 ROT 失败（HTTP ${res.status}）`);
}

export async function setRotEnabled(
  token: string,
  name: string,
  enabled: boolean,
): Promise<void> {
  const res = await fetch(
    `/api/resources/pot/rot/${encodeURIComponent(name)}/enabled`,
    {
      method: 'POST',
      headers: {
        [TOKEN_HEADER]: token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ enabled }),
    },
  );
  if (!res.ok) throw new Error(`切换 ROT 失败（HTTP ${res.status}）`);
}

export async function cancelSchedule(
  token: string,
  id: string,
): Promise<void> {
  const res = await fetch(`/api/schedule/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`取消定时任务失败（HTTP ${res.status}）`);
}

export async function startBackgroundTask(
  token: string,
  command: string,
): Promise<{ task_id: string }> {
  const res = await fetch('/api/tasks', {
    method: 'POST',
    headers: {
      [TOKEN_HEADER]: token,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ command }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `启动后台任务失败（HTTP ${res.status}）`);
  }
  return (await res.json()) as { task_id: string };
}

export async function cancelBackgroundTask(
  token: string,
  id: string,
): Promise<void> {
  const res = await fetch(`/api/tasks/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`取消后台任务失败（HTTP ${res.status}）`);
}

export async function removeBackgroundTask(
  token: string,
  id: string,
): Promise<void> {
  const res = await fetch(`/api/tasks/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { [TOKEN_HEADER]: token },
  });
  if (!res.ok) throw new Error(`删除后台任务失败（HTTP ${res.status}）`);
}
