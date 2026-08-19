import { useState } from 'react';

interface Props {
  busy: boolean;
  listening: boolean;
  transcribing: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onStartVoice: () => void;
  onStopVoice: () => void;
}

export function CommandBar({
  busy,
  listening,
  transcribing,
  onSend,
  onStop,
  onStartVoice,
  onStopVoice,
}: Props) {
  const [text, setText] = useState('');

  const submit = () => {
    const value = text.trim();
    if (!value) return;
    onSend(value);
    setText('');
  };

  return (
    <div className="command-bar">
      {busy && (
        <button type="button" className="stop" onClick={onStop}>
          停止
        </button>
      )}
      <input
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit();
        }}
        placeholder="输入命令，如：打开记事本并输入 hello"
        enterKeyHint="send"
      />
      <button
        type="button"
        className={listening ? 'mic active' : 'mic'}
        onClick={listening ? onStopVoice : onStartVoice}
        title="语音输入"
        aria-label="语音输入"
      >
        {transcribing ? '…' : listening ? '⏹' : '🎤'}
      </button>
      <button type="button" className="send" onClick={submit} disabled={!text.trim()}>
        SEND
      </button>
    </div>
  );
}
