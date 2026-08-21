import type { DanmakuDensity, DanmakuIntensity, DanmakuSize } from '../types';

interface Props {
  density: DanmakuDensity;
  size: DanmakuSize;
  intensity: DanmakuIntensity;
  onChangeDensity: (value: DanmakuDensity) => void;
  onChangeSize: (value: DanmakuSize) => void;
  onChangeIntensity: (value: DanmakuIntensity) => void;
  onClose: () => void;
}

interface Option<T extends string> {
  value: T;
  label: string;
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? 'active' : ''}
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function DanmakuPanel({
  density,
  size,
  intensity,
  onChangeDensity,
  onChangeSize,
  onChangeIntensity,
  onClose,
}: Props) {
  return (
    <div className="danmaku-panel" role="dialog" aria-label="弹幕设置">
      <div className="danmaku-panel-head">
        <span>弹幕设置</span>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="关闭弹幕设置"
        >
          ✕
        </button>
      </div>

      <div className="setting-row">
        <span className="setting-label">密度</span>
        <Segmented
          value={density}
          options={[
            { value: 'all', label: '全部' },
            { value: 'key', label: '关键' },
            { value: 'minimal', label: '少量' },
          ]}
          onChange={onChangeDensity}
        />
      </div>

      <div className="setting-row">
        <span className="setting-label">字号</span>
        <Segmented
          value={size}
          options={[
            { value: 'small', label: '小' },
            { value: 'medium', label: '中' },
            { value: 'large', label: '大' },
          ]}
          onChange={onChangeSize}
        />
      </div>

      <div className="setting-row">
        <span className="setting-label">浓度</span>
        <Segmented
          value={intensity}
          options={[
            { value: 'light', label: '淡' },
            { value: 'standard', label: '标准' },
            { value: 'strong', label: '深' },
          ]}
          onChange={onChangeIntensity}
        />
      </div>
    </div>
  );
}
