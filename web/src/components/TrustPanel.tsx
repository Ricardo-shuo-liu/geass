import type { PrivacyMask, SensitiveRegion, TrustSettings } from '../types';

interface Props {
  settings: TrustSettings;
  masks: PrivacyMask[];
  masksEnabled: boolean;
  maskMode: boolean;
  suggestions: SensitiveRegion[];
  detecting: boolean;
  detectNote?: string | null;
  onUpdate: (patch: {
    mode?: TrustSettings['mode'];
    visual_delay_ms?: number;
    overrides?: Record<string, 'auto' | 'confirm' | null>;
    task_allow_all?: boolean;
  }) => void;
  onToggleMaskMode: () => void;
  onToggleMasks: (enabled: boolean) => void;
  onDeleteMask: (id: string) => void;
  onClearMasks: () => void;
  onDetect: () => void;
  onApplySuggestion: (index: number) => void;
  onApplyAllSuggestions: () => void;
  onDismissSuggestions: () => void;
  onClose: () => void;
}

const MODES: Array<{ id: TrustSettings['mode']; label: string; hint: string }> = [
  { id: 'smart', label: '智能', hint: '操作可视化，仅高危动作等待确认' },
  { id: 'confirm', label: '全部确认', hint: '每个动作都在屏幕上等待确认' },
  { id: 'off', label: '全部放行', hint: '不显示预览也不等待，仅保留终端安全审核' },
];

export function TrustPanel({
  settings,
  masks,
  masksEnabled,
  maskMode,
  suggestions,
  detecting,
  detectNote,
  onUpdate,
  onToggleMaskMode,
  onToggleMasks,
  onDeleteMask,
  onClearMasks,
  onDetect,
  onApplySuggestion,
  onApplyAllSuggestions,
  onDismissSuggestions,
  onClose,
}: Props) {
  const overrides = Object.entries(settings.overrides);
  return (
    <section className="trust-panel" aria-label="信任设置">
      <div className="panel-head">
        <span>信任与隐私</span>
        <button type="button" onClick={onClose} aria-label="关闭信任设置">
          ✕
        </button>
      </div>

      <div className="trust-section">
        <h3>动作预览</h3>
        <div className="segmented trust-modes">
          {MODES.map((item) => (
            <button
              type="button"
              key={item.id}
              className={settings.mode === item.id ? 'active' : ''}
              onClick={() => onUpdate({ mode: item.id })}
              title={item.hint}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="trust-hint">
          {MODES.find((item) => item.id === settings.mode)?.hint}
        </p>
        <label className="trust-row">
          <span>可视化延迟</span>
          <input
            type="range"
            min={0}
            max={2000}
            step={100}
            value={settings.visual_delay_ms}
            onChange={(event) =>
              onUpdate({ visual_delay_ms: Number(event.target.value) })
            }
          />
          <span>{settings.visual_delay_ms}ms</span>
        </label>
        <label className="trust-row">
          <input
            type="checkbox"
            checked={settings.task_allow_all}
            onChange={(event) => onUpdate({ task_allow_all: event.target.checked })}
          />
          <span>本任务全部放行（新任务自动关闭）</span>
        </label>
        {overrides.length > 0 && (
          <div className="trust-overrides">
            <span className="trust-hint">工具覆盖</span>
            {overrides.map(([tool, value]) => (
              <div className="trust-override" key={tool}>
                <span>{tool}</span>
                <select
                  value={value}
                  onChange={(event) =>
                    onUpdate({ overrides: { [tool]: event.target.value as 'auto' | 'confirm' } })
                  }
                >
                  <option value="auto">始终允许</option>
                  <option value="confirm">始终询问</option>
                </select>
                <button
                  type="button"
                  onClick={() => onUpdate({ overrides: { [tool]: null } })}
                  aria-label={`移除 ${tool} 覆盖`}
                >
                  移除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="trust-section">
        <h3>隐私遮罩</h3>
        <label className="trust-row">
          <input
            type="checkbox"
            checked={masksEnabled}
            onChange={(event) => onToggleMasks(event.target.checked)}
          />
          <span>启用遮罩（推流、模型与 OCR 同步打码）</span>
        </label>
        <button
          type="button"
          className={maskMode ? 'trust-draw active' : 'trust-draw'}
          onClick={onToggleMaskMode}
        >
          {maskMode ? '框选模式：在画面上拖动' : '框选遮罩区域'}
        </button>
        {maskMode && (
          <button type="button" className="trust-cancel" onClick={onToggleMaskMode}>
            取消框选
          </button>
        )}
        <button
          type="button"
          className="trust-draw"
          disabled={detecting}
          onClick={onDetect}
        >
          {detecting ? '识别中…' : '自动识别敏感区域'}
        </button>
        {detectNote && <p className="trust-hint">{detectNote}</p>}
        {masks.length === 0 && <p className="trust-hint">暂无遮罩区域</p>}
        {masks.map((mask) => (
          <div className="trust-override" key={mask.id}>
            <span>
              {mask.x.toFixed(2)}, {mask.y.toFixed(2)} · {mask.w.toFixed(2)}×
              {mask.h.toFixed(2)}
            </span>
            <button type="button" onClick={() => onDeleteMask(mask.id)}>
              删除
            </button>
          </div>
        ))}
        {masks.length > 0 && (
          <button type="button" className="trust-clear" onClick={onClearMasks}>
            清空全部遮罩（{masks.length}）
          </button>
        )}
        {suggestions.length > 0 && (
          <div className="trust-suggestions">
            <p className="trust-hint">
              识别到 {suggestions.length} 个建议区域（密码框 / 敏感关键词），应用后即生效
            </p>
            {suggestions.map((region, index) => (
              <div className="trust-override" key={`${region.source}-${index}`}>
                <span>
                  {region.source === 'password' ? '密码框' : '关键词'} · {region.label}
                </span>
                <button type="button" onClick={() => onApplySuggestion(index)}>
                  应用
                </button>
              </div>
            ))}
            <div className="trust-suggestion-actions">
              <button type="button" onClick={onApplyAllSuggestions}>
                全部应用
              </button>
              <button type="button" onClick={onDismissSuggestions}>
                忽略
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
