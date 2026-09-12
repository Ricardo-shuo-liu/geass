function sessionStore(): Storage | null {
  try {
    return window.sessionStorage ?? null;
  } catch {
    return null;
  }
}

/** 读取当前浏览器会话的 Token（隐私模式下可能不可用）。 */
export function readSessionToken(key: string): string | null {
  try {
    return sessionStore()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writeSessionToken(key: string, value: string): void {
  try {
    sessionStore()?.setItem(key, value);
  } catch {
    // 存储不可用时退化为仅内存保存
  }
}

export function clearSessionToken(key: string): void {
  try {
    sessionStore()?.removeItem(key);
  } catch {
    // 忽略存储不可用
  }
}

/** 清理旧版本遗留的 localStorage Token。 */
export function clearLegacyToken(key: string): void {
  try {
    localStorage?.removeItem(key);
  } catch {
    // 忽略存储不可用
  }
}
