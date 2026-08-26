import { useCallback, useEffect, useState } from 'react';
import {
  addRagSource,
  cancelBackgroundTask,
  cancelSchedule,
  clearMemory,
  deleteMemoryEntry,
  deleteRot,
  deleteSkill,
  getResources,
  reindexRag,
  removeBackgroundTask,
  removeRagSource,
  setRagEnabled,
  setRotEnabled,
  startBackgroundTask,
} from '../api';
import type { ResourceSummary } from '../types';

interface Props {
  token: string;
  onClose: () => void;
}

type Tab = 'memory' | 'rag' | 'skills' | 'pot' | 'schedule' | 'background';

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'memory', label: '记忆' },
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
