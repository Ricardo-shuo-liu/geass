import { useCallback, useEffect, useState } from 'react';
import {
  addMcpServer,
  addRagSource,
  cancelBackgroundTask,
  cancelSchedule,
  clearMemory,
  deleteMcpServer,
  deleteMemoryEntry,
  deleteRot,
  deleteSkill,
  getResources,
  reindexRag,
  removeBackgroundTask,
  removeRagSource,
  setMcpServerEnabled,
  setMcpToolEnabled,
  setRagEnabled,
  setRotEnabled,
  startBackgroundTask,
  testMcpServer,
} from '../api';
import type { McpAddInput, ResourceSummary } from '../types';

interface Props {
  token: string;
  onClose: () => void;
}

type Tab =
  | 'memory'
  | 'mcp'
  | 'rag'
  | 'skills'
  | 'pot'
  | 'schedule'
  | 'background';

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'memory', label: '记忆' },
  { id: 'mcp', label: 'MCP' },
  { id: 'rag', label: 'RAG' },
  { id: 'skills', label: '技能' },
  { id: 'pot', label: 'POT' },
  { id: 'schedule', label: '定时' },
  { id: 'background', label: '后台' },
];

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ResourcePanel({ token, onClose }: Props) {
  const [data, setData] = useState<ResourceSummary | null>(null);
  const [tab, setTab] = useState<Tab>('memory');
  const [error, setError] = useState<string | null>(null);
  const [ragPath, setRagPath] = useState('');
  const [ragName, setRagName] = useState('');
  const [ragExts, setRagExts] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await getResources(token));
      setError(null);
    } catch (loadError) {
      setError(errorText(loadError));
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (action: () => Promise<void>) => {
    try {
      await action();
      await load();
    } catch (actionError) {
      setError(errorText(actionError));
    }
  };

  const addRag = () => {
    if (!ragPath.trim()) return;
    void run(() =>
      addRagSource(token, ragPath.trim(), ragName.trim() || undefined, ragExts.trim() || undefined),
    );
    setRagPath('');
    setRagName('');
    setRagExts('');
  };

  return (
    <div className="resource-backdrop" onClick={onClose}>
      <div
        className="resource-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="resource-modal-head">
          <span>资源管理</span>
          <button
            type="button"
            className="resource-close"
            onClick={onClose}
            aria-label="关闭资源面板"
          >
            ✕
          </button>
        </div>
        <div className="resource-modal-body">
          <nav className="resource-nav">
            {TABS.map((item) => (
              <button
                type="button"
                key={item.id}
                className={tab === item.id ? 'active' : ''}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="resource-content">
            {error && <div className="resource-error">{error}</div>}
            {tab === 'memory' && (
              <MemoryTab data={data} token={token} run={run} />
            )}
            {tab === 'mcp' && (
              <McpTab data={data} token={token} run={run} reload={load} />
            )}
            {tab === 'rag' && (
              <RagTab
                data={data}
                token={token}
                run={run}
                ragPath={ragPath}
                ragName={ragName}
                ragExts={ragExts}
                onPath={setRagPath}
                onName={setRagName}
                onExts={setRagExts}
                onAdd={addRag}
              />
            )}
            {tab === 'skills' && (
              <SkillsTab data={data} token={token} run={run} />
            )}
            {tab === 'pot' && <PotTab data={data} token={token} run={run} />}
            {tab === 'schedule' && (
              <ScheduleTab data={data} token={token} run={run} />
            )}
            {tab === 'background' && (
              <BackgroundTab data={data} token={token} run={run} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface TabProps {
  data: ResourceSummary | null;
  token: string;
  run: (action: () => Promise<void>) => Promise<void>;
}

function MemoryTab({ data, token, run }: TabProps) {
  const entries = data?.memory.entries ?? [];
  return (
    <div className="resource-list">
      <button
        type="button"
        className="resource-danger"
        onClick={() => {
          if (window.confirm('清空全部持久记忆？')) void run(() => clearMemory(token));
        }}
      >
        清空记忆
      </button>
      {entries.length === 0 && <div className="resource-empty">暂无记忆</div>}
      {entries.map((entry) => (
        <div className="resource-item" key={entry.key}>
          <div className="resource-item-main">
            <span className="resource-key">{entry.key}</span>
            <span className="resource-value">{entry.value}</span>
          </div>
          <button
            type="button"
            className="resource-mini"
            onClick={() => void run(() => deleteMemoryEntry(token, entry.key))}
          >
            删除
          </button>
        </div>
      ))}
    </div>
  );
}

interface McpTabProps extends TabProps {
  reload: () => Promise<void>;
}

function splitLines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function kvLines(text: string, separator: '=' | ':'): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of splitLines(text)) {
    const index = line.indexOf(separator);
    if (index <= 0) throw new Error(`无法解析：${line}`);
    result[line.slice(0, index).trim()] = line.slice(index + 1).trim();
  }
  return result;
}

function mcpStatus(server: { verified: boolean; enabled: boolean }): string {
  if (!server.verified) return '未通过测试';
  return server.enabled ? '启用中' : '已停用';
}

function McpTab({ data, token, run, reload }: McpTabProps) {
  const servers = data?.mcp?.servers ?? [];
  const [transport, setTransport] = useState<'stdio' | 'http'>('stdio');
  const [name, setName] = useState('');
  const [command, setCommand] = useState('');
  const [argsText, setArgsText] = useState('');
  const [cwd, setCwd] = useState('');
  const [envText, setEnvText] = useState('');
  const [url, setUrl] = useState('');
  const [headersText, setHeadersText] = useState('');
  const [jsonText, setJsonText] = useState('');
  const [testing, setTesting] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [localError, setLocalError] = useState('');

  const runLong = async (
    action: () => Promise<string | void>,
    label: string,
  ) => {
    setTesting(label);
    setNotice('');
    setLocalError('');
    try {
      const message = await action();
      if (message) setNotice(message);
      await reload();
    } catch (actionError) {
      setLocalError(errorText(actionError));
    } finally {
      setTesting(null);
    }
  };

  const addFromForm = () => {
    const inputName = name.trim();
    if (!inputName) {
      setLocalError('请输入服务器名称');
      return;
    }
    const input: McpAddInput = {
      name: inputName,
      transport,
      command: transport === 'stdio' ? command.trim() : undefined,
      args: transport === 'stdio' ? splitLines(argsText) : undefined,
      cwd: transport === 'stdio' ? cwd.trim() || undefined : undefined,
      env: transport === 'stdio' ? kvLines(envText, '=') : undefined,
      url: transport === 'http' ? url.trim() : undefined,
      headers: transport === 'http' ? kvLines(headersText, ':') : undefined,
    };
    void runLong(async () => {
      const result = await addMcpServer(token, input);
      return result.record.verified
        ? `「${result.record.name}」导入并测试通过，已启用`
        : `「${result.record.name}」测试失败，已保留为停用：${
            result.record.last_error || '连接失败'
          }`;
    }, inputName);
  };

  const importJson = () => {
    let entries: Record<string, Record<string, unknown>>;
    try {
      const parsed = JSON.parse(jsonText) as {
        mcpServers?: Record<string, Record<string, unknown>>;
      };
      entries = parsed.mcpServers ?? (parsed as Record<string, Record<string, unknown>>);
    } catch (jsonError) {
      setLocalError(errorText(jsonError));
      return;
    }
    void runLong(async () => {
      let succeeded = 0;
      let failed = 0;
      for (const [entryName, entry] of Object.entries(entries)) {
        const entryTransport =
          entry.type === 'http' || entry.url
            ? 'http'
            : (entry.type as string) === 'stdio' || !entry.type
              ? 'stdio'
              : null;
        if (!entryTransport) {
          failed += 1;
          continue;
        }
        try {
          const result = await addMcpServer(token, {
            name: entryName,
            transport: entryTransport,
            command: typeof entry.command === 'string' ? entry.command : undefined,
            args: Array.isArray(entry.args)
              ? entry.args.map(String)
              : undefined,
            cwd: typeof entry.cwd === 'string' ? entry.cwd : undefined,
            env:
              entry.env && typeof entry.env === 'object'
                ? (entry.env as Record<string, string>)
                : undefined,
            url: typeof entry.url === 'string' ? entry.url : undefined,
            headers:
              entry.headers && typeof entry.headers === 'object'
                ? (entry.headers as Record<string, string>)
                : undefined,
          });
          if (result.record.verified) {
            succeeded += 1;
          } else {
            failed += 1;
          }
        } catch {
          failed += 1;
        }
      }
      return `JSON 导入完成：成功 ${succeeded} 个，失败/保留 ${failed} 个`;
    }, 'JSON 导入');
  };

  const retest = (serverName: string) => {
    void runLong(async () => {
      const result = await testMcpServer(token, serverName);
      return result.record.verified
        ? `「${serverName}」测试通过`
        : `「${serverName}」仍无法连接：${result.record.last_error || ''}`;
    }, serverName);
  };

  return (
    <div className="resource-list">
      <details className="resource-details">
        <summary>添加 MCP 服务器</summary>
        <div className="resource-form">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="服务器名称，如 github"
          />
          <select
            value={transport}
            onChange={(event) =>
              setTransport(event.target.value as 'stdio' | 'http')
            }
          >
            <option value="stdio">stdio（本地命令）</option>
            <option value="http">Streamable HTTP</option>
          </select>
          {transport === 'stdio' ? (
            <>
              <input
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                placeholder="命令，如 npx 或 uvx"
              />
              <textarea
                value={argsText}
                onChange={(event) => setArgsText(event.target.value)}
                placeholder="参数（每行一个），如 mcp-server-github"
              />
              <input
                value={cwd}
                onChange={(event) => setCwd(event.target.value)}
                placeholder="工作目录（可选）"
              />
              <textarea
                value={envText}
                onChange={(event) => setEnvText(event.target.value)}
                placeholder="环境变量（每行 K=V，可选）"
              />
            </>
          ) : (
            <>
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/mcp"
              />
              <textarea
                value={headersText}
                onChange={(event) => setHeadersText(event.target.value)}
                placeholder="Header（每行 Key: Value，可选）"
              />
            </>
          )}
          <button
            type="button"
            className="resource-add"
            disabled={testing !== null}
            onClick={addFromForm}
          >
            {testing === name ? '测试中…' : '导入并测试'}
          </button>
          <textarea
            value={jsonText}
            onChange={(event) => setJsonText(event.target.value)}
            placeholder='或直接粘贴 Claude/Cursor JSON：{"mcpServers": {...}}'
          />
          <button
            type="button"
            className="resource-add"
            disabled={testing !== null}
            onClick={importJson}
          >
            导入 JSON
          </button>
        </div>
      </details>
      {localError && <div className="resource-error">{localError}</div>}
      {notice && <div className="resource-value">{notice}</div>}
      {servers.length === 0 && <div className="resource-empty">暂无 MCP 服务器</div>}
      {servers.map((server) => (
        <div className="resource-server" key={server.id}>
          <div className="resource-item">
            <div className="resource-item-main">
              <span className="resource-key">
                {server.name} · {mcpStatus(server)}
              </span>
              <span className="resource-value">
                {server.transport === 'stdio'
                  ? `${server.command || ''} ${(server.args || []).join(' ')}`
                  : server.url}
                {' · '}
                {server.tools.length} 个工具
              </span>
              {server.last_error && (
                <span className="resource-value">错误：{server.last_error}</span>
              )}
            </div>
            <div className="resource-actions">
              <button
                type="button"
                className="resource-mini"
                disabled={testing !== null}
                onClick={() => retest(server.name)}
              >
                {testing === server.name ? '测试中…' : '测试'}
              </button>
              {server.verified && (
                <button
                  type="button"
                  className="resource-mini"
                  onClick={() =>
                    void run(() =>
                      setMcpServerEnabled(token, server.name, !server.enabled),
                    )
                  }
                >
                  {server.enabled ? '停用' : '启用'}
                </button>
              )}
              <button
                type="button"
                className="resource-mini danger"
                onClick={() => {
                  if (
                    window.confirm(
                      `永久删除 MCP 服务器「${server.name}」及其全部工具配置？`,
                    )
                  ) {
                    void run(() => deleteMcpServer(token, server.name));
                  }
                }}
              >
                删除
              </button>
            </div>
          </div>
          {server.tools.length > 0 && (
            <details className="resource-details">
              <summary>工具（{server.tools.length}）</summary>
              {server.tools.map((tool) => (
                <div className="resource-item" key={`${server.id}:${tool.id}`}>
                  <div className="resource-item-main">
                    <span className="resource-key">{tool.name}</span>
                    <span className="resource-value">{tool.description || '无描述'}</span>
                  </div>
                  <button
                    type="button"
                    className="resource-mini"
                    onClick={() =>
                      void run(() =>
                        setMcpToolEnabled(
                          token,
                          server.name,
                          tool.id,
                          !tool.enabled,
                        ),
                      )
                    }
                  >
                    {tool.enabled ? '停用' : '启用'}
                  </button>
                </div>
              ))}
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

function RagTab({
  data,
  token,
  run,
  ragPath,
  ragName,
  ragExts,
  onPath,
  onName,
  onExts,
  onAdd,
}: TabProps & {
  ragPath: string;
  ragName: string;
  ragExts: string;
  onPath: (value: string) => void;
  onName: (value: string) => void;
  onExts: (value: string) => void;
  onAdd: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const sources = data?.rag.sources ?? [];
  return (
    <div className="resource-list">
      <button
        type="button"
        className="resource-add"
        onClick={() => setShowForm((value) => !value)}
      >
        {showForm ? '收起' : '＋ 添加数据源'}
      </button>
      {showForm && (
        <div className="resource-form">
          <input
            value={ragPath}
            onChange={(event) => onPath(event.target.value)}
            placeholder="本机路径，如 /home/user/notes"
          />
          <input
            value={ragName}
            onChange={(event) => onName(event.target.value)}
            placeholder="别名（可选）"
          />
          <input
            value={ragExts}
            onChange={(event) => onExts(event.target.value)}
            placeholder="后缀，如 .md,.txt（可选）"
          />
          <button
            type="button"
            className="resource-add"
            onClick={() => {
              onAdd();
              setShowForm(false);
            }}
          >
            添加
          </button>
        </div>
      )}
      {sources.length === 0 && <div className="resource-empty">暂无 RAG 数据源</div>}
      {sources.map((source) => (
        <div className="resource-item" key={source.id}>
          <div className="resource-item-main">
            <span className="resource-key">{source.name}</span>
            <span className="resource-value">
              {source.mode} · {source.files} 文件 / {source.chunks} 分块
              {source.needs_reindex ? ' · 需重建' : ''}
            </span>
          </div>
          <div className="resource-actions">
            <button
              type="button"
              className="resource-mini"
              onClick={() =>
                void run(() => setRagEnabled(token, source.name, !source.enabled))
              }
            >
              {source.enabled ? '停用' : '启用'}
            </button>
            <button
              type="button"
              className="resource-mini"
              onClick={() => void run(() => reindexRag(token, source.name))}
            >
              重建
            </button>
            <button
              type="button"
              className="resource-mini danger"
              onClick={() => {
                if (window.confirm(`删除数据源「${source.name}」的 RAG 镜像？`)) {
                  void run(() => removeRagSource(token, source.name));
                }
              }}
            >
              删除
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function SkillsTab({ data, token, run }: TabProps) {
  const skills = data?.skills ?? [];
  return (
    <div className="resource-list">
      {skills.length === 0 && <div className="resource-empty">暂无技能</div>}
      {skills.map((skill) => (
        <div className="resource-item" key={skill.name}>
          <div className="resource-item-main">
            <span className="resource-key">
              {skill.name}
              {skill.system ? ' · 系统' : ' · 进化'}
            </span>
            <span className="resource-value">{skill.description}</span>
          </div>
          <button
            type="button"
            className="resource-mini danger"
            onClick={() => {
              if (window.confirm(`删除技能「${skill.name}」？系统技能会在下次同步恢复。`)) {
                void run(() => deleteSkill(token, skill.name));
              }
            }}
          >
            删除
          </button>
        </div>
      ))}
    </div>
  );
}

function PotTab({ data, token, run }: TabProps) {
  const rots = data?.pot.rots ?? [];
  const cot = data?.pot.cot ?? '';
  return (
    <div className="resource-list">
      <details className="resource-details">
        <summary>Global-COT（{cot ? '已生成' : '空'}）</summary>
        <pre className="resource-pre">{cot || '（暂无）'}</pre>
      </details>
      {rots.length === 0 && <div className="resource-empty">暂无 ROT</div>}
      {rots.map((rot) => (
        <div className="resource-item" key={rot.name}>
          <div className="resource-item-main">
            <span className="resource-key">
              {rot.name} · {rot.role}
            </span>
            <span className="resource-value">{rot.description}</span>
          </div>
          <div className="resource-actions">
            <button
              type="button"
              className="resource-mini"
              onClick={() =>
                void run(() => setRotEnabled(token, rot.name, !rot.enabled))
              }
            >
              {rot.enabled ? '停用' : '启用'}
            </button>
            <button
              type="button"
              className="resource-mini danger"
              onClick={() => {
                if (window.confirm(`删除 ROT「${rot.name}」？`)) {
                  void run(() => deleteRot(token, rot.name));
                }
              }}
            >
              删除
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function ScheduleTab({ data, token, run }: TabProps) {
  const jobs = data?.schedule.jobs ?? [];
  return (
    <div className="resource-list">
      {jobs.length === 0 && <div className="resource-empty">暂无定时任务</div>}
      {jobs.map((job) => (
        <div className="resource-item" key={job.id}>
          <div className="resource-item-main">
            <span className="resource-key">
              {job.status} · {new Date(job.run_at * 1000).toLocaleString('zh-CN')}
            </span>
            <span className="resource-value">{job.command}</span>
          </div>
          {job.status === 'pending' && (
            <button
              type="button"
              className="resource-mini danger"
              onClick={() => void run(() => cancelSchedule(token, job.id))}
            >
              取消
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

const BACKGROUND_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  cancelling: '取消中',
  done: '完成',
  error: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
  limit: '超步数',
};

function BackgroundTab({ data, token, run }: TabProps) {
  const [command, setCommand] = useState('');
  const tasks = data?.background.tasks ?? [];
  return (
    <div className="resource-list">
      <div className="resource-form">
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="后台执行的命令，如：把 notes 加入 RAG"
        />
        <button
          type="button"
          className="resource-add"
          onClick={() => {
            const value = command.trim();
            if (!value) return;
            void run(() =>
              startBackgroundTask(token, value).then(() => setCommand('')),
            );
          }}
        >
          开始后台任务
        </button>
      </div>
      {tasks.length === 0 && (
        <div className="resource-empty">暂无后台任务</div>
      )}
      {tasks.map((task) => (
        <div className="resource-item" key={task.id}>
          <div className="resource-item-main">
            <span className="resource-key">
              {BACKGROUND_LABELS[task.status] ?? task.status} ·{' '}
              {new Date(task.created_at * 1000).toLocaleString('zh-CN')}
            </span>
            <span className="resource-value">{task.command}</span>
            {task.result?.message && (
              <span className="resource-value">结果：{task.result.message}</span>
            )}
          </div>
          <div className="resource-actions">
            {(task.status === 'pending' || task.status === 'running') && (
              <button
                type="button"
                className="resource-mini"
                onClick={() => void run(() => cancelBackgroundTask(token, task.id))}
              >
                取消
              </button>
            )}
            <button
              type="button"
              className="resource-mini danger"
              onClick={() => void run(() => removeBackgroundTask(token, task.id))}
            >
              删除
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
