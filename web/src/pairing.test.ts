import { afterEach, describe, expect, it } from 'vitest';

import { clearPairCode, readPairCode } from './pairing';

describe('pairing hash helpers', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('reads a pairing code from the hash', () => {
    expect(readPairCode('#pair=abc123')).toBe('abc123');
    expect(readPairCode('pair=abc123&other=1')).toBe('abc123');
  });

  it('returns null when no code is present', () => {
    expect(readPairCode('')).toBeNull();
    expect(readPairCode('#other=1')).toBeNull();
    expect(readPairCode('#pair=')).toBeNull();
  });

  it('clears the pairing hash from the address bar', () => {
    window.history.replaceState(null, '', '/index.html?x=1#pair=abc123');

    clearPairCode();

    expect(window.location.hash).toBe('');
    expect(window.location.search).toBe('?x=1');
  });
});
