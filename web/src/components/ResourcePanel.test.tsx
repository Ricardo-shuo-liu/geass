import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ResourceSummary } from '../types';
import { ResourcePanel } from './ResourcePanel';

const mocks = vi.hoisted(() => ({
  addMcpServer: vi.fn(),
  addRagSource: vi.fn(),
  cancelBackgroundTask: vi.fn(),
  cancelSchedule: vi.fn(),
  clearMemory: vi.fn(),
  deleteMcpServer: vi.fn(),
  deleteMemoryEntry: vi.fn(),
  deleteRot: vi.fn(),
  deleteSkill: vi.fn(),
  getResources: vi.fn(),
  reindexRag: vi.fn(),
  removeBackgroundTask: vi.fn(),
  removeRagSource: vi.fn(),
  setMcpServerEnabled: vi.fn(),
  setMcpToolEnabled: vi.fn(),
  setRagEnabled: vi.fn(),
  setRotEnabled: vi.fn(),
  startBackgroundTask: vi.fn(),
  testMcpServer: vi.fn(),
}));

vi.mock('../api', () => mocks);

const summary = {
  memory: { enabled: true, entries: [] },
  rag: { enabled: true, sources: [] },
  skills: [],
  pot: { enabled: true, cot: '', rots: [] },
  schedule: { jobs: [] },
  background: { enabled: true, max: 5, tasks: [] },
  mcp: {
    enabled: true,
    servers: [
      {
        id: 's1',
        name: 'demo',
        transport: 'stdio' as const,
        enabled: true,
        verified: true,
        command: 'echo',
        args: [],
        tools: [
          {
            id: 'add',
            name: 'add',
            description: '相加',
            enabled: true,
          },
        ],
      },
    ],
  },
} as ResourceSummary;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getResources.mockResolvedValue(summary);
  mocks.addMcpServer.mockResolvedValue({ record: summary.mcp.servers[0] });
  mocks.testMcpServer.mockResolvedValue({ record: summary.mcp.servers[0] });
  mocks.setMcpServerEnabled.mockResolvedValue(undefined);
  mocks.setMcpToolEnabled.mockResolvedValue(undefined);
  mocks.deleteMcpServer.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
});

describe('ResourcePanel MCP', () => {
  it('shows the MCP tab with servers and per-tool actions', async () => {
    render(<ResourcePanel token="tok" onClose={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'MCP' }));
    expect(await screen.findByText('demo · 启用中')).toBeInTheDocument();
    expect(
      screen.getByText((_content, element) => {
        const node = element as HTMLElement | null;
        return (
          node?.classList?.contains('resource-value') === true &&
          node.textContent?.includes('1 个工具') === true
        );
      }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByText((_content, element) => {
        const node = element as HTMLElement | null;
        return (
          node?.tagName === 'SUMMARY' &&
          node.textContent?.includes('工具（1）') === true
        );
      }),
    );
    const toolRow = screen.getByText('add').closest('.resource-item');
    expect(toolRow).not.toBeNull();

    const toggle = toolRow?.querySelector('button');
    expect(toggle).not.toBeNull();
    fireEvent.click(toggle as HTMLButtonElement);

    await waitFor(() =>
      expect(mocks.setMcpToolEnabled).toHaveBeenCalledWith(
        'tok',
        'demo',
        'add',
        false,
      ),
    );
  });

  it('imports a stdio server through the form', async () => {
    render(<ResourcePanel token="tok" onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'MCP' }));

    fireEvent.change(
      await screen.findByPlaceholderText('服务器名称，如 github'),
      { target: { value: 'new-server' } },
    );
    fireEvent.change(screen.getByPlaceholderText('命令，如 npx 或 uvx'), {
      target: { value: 'echo' },
    });
    fireEvent.click(screen.getByRole('button', { name: '导入并测试' }));

    await waitFor(() => expect(mocks.addMcpServer).toHaveBeenCalled());
    expect(mocks.addMcpServer.mock.calls[0][0]).toBe('tok');
    expect(mocks.addMcpServer.mock.calls[0][1]).toMatchObject({
      name: 'new-server',
      command: 'echo',
      transport: 'stdio',
    });
  });

  it('confirms before permanently deleting a server', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ResourcePanel token="tok" onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'MCP' }));
    await screen.findByText('demo · 启用中');

    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() =>
      expect(mocks.deleteMcpServer).toHaveBeenCalledWith('tok', 'demo'),
    );
    confirm.mockRestore();
  });
});
