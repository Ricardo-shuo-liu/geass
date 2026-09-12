const PAIR_PARAM = 'pair';

/** 从 location.hash 中读取一次性配对码；不存在时返回 null。 */
export function readPairCode(hash: string): string | null {
  const raw = String(hash || '').replace(/^#/, '');
  if (!raw) return null;
  const params = new URLSearchParams(raw);
  const code = (params.get(PAIR_PARAM) || '').trim();
  return code || null;
}

/** 清掉地址栏中的配对码，避免留在浏览器历史里。 */
export function clearPairCode(): void {
  if (typeof window === 'undefined' || !window.history?.replaceState) return;
  const { pathname, search } = window.location;
  window.history.replaceState(null, '', `${pathname}${search}`);
}
