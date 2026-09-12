import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ScreenView, contentRect, rectFromPoints } from './ScreenView';

const RECT = {
  x: 0,
  y: 0,
  width: 1000,
  height: 500,
  top: 0,
  left: 0,
  right: 1000,
  bottom: 500,
  toJSON: () => ({}),
};

class FakePointerEvent extends MouseEvent {
  pointerId: number;

  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
  }
}

beforeEach(() => {
  vi.stubGlobal('PointerEvent', FakePointerEvent);
  vi.stubGlobal('createImageBitmap', async () => ({
    width: 1000,
    height: 500,
    close: () => {},
  }));
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue(
    RECT as DOMRect,
  );
  vi.spyOn(HTMLDivElement.prototype, 'getBoundingClientRect').mockReturnValue(
    RECT as DOMRect,
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => null as never,
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ScreenView overlay', () => {
  it('computes the letterboxed content rect', () => {
    expect(contentRect({ width: 800, height: 800 }, 1000, 500)).toEqual({
      left: 0,
      top: 200,
      width: 800,
      height: 400,
    });
    expect(contentRect({ width: 0, height: 0 }, 1000, 500)).toBeNull();
  });

  it('normalizes a drawn rectangle regardless of drag direction', () => {
    expect(rectFromPoints(0.6, 0.7, 0.2, 0.3)).toEqual({
      x: 0.2,
      y: 0.3,
      w: expect.closeTo(0.4, 5),
      h: expect.closeTo(0.4, 5),
    });
  });

  it('renders masks and preview markers', async () => {
    render(
      <ScreenView
        frame={new Blob(['x'])}
        masks={[{ id: 'm1', x: 0.1, y: 0.2, w: 0.3, h: 0.4 }]}
        masksEnabled
        preview={{ kind: 'point', target: { x: 0.25, y: 0.5 } }}
      />,
    );

    await waitFor(() =>
      expect(screen.getByTestId('screen-overlay')).toBeInTheDocument(),
    );
    expect(document.querySelector('.privacy-mask.active')).not.toBeNull();
    expect(screen.getByTestId('preview-point')).toBeInTheDocument();
  });

  it('hides mask boxes when masking is disabled', async () => {
    render(
      <ScreenView
        frame={new Blob(['x'])}
        masks={[{ id: 'm1', x: 0.1, y: 0.2, w: 0.3, h: 0.4 }]}
        masksEnabled={false}
      />,
    );

    await waitFor(() =>
      expect(screen.getByTestId('screen-overlay')).toBeInTheDocument(),
    );
    expect(document.querySelector('.privacy-mask')).toBeNull();
  });

  it('creates a mask rectangle from a drag', async () => {
    const onMaskCreate = vi.fn();
    render(<ScreenView frame={new Blob(['x'])} maskMode onMaskCreate={onMaskCreate} />);
    const overlay = await screen.findByTestId('screen-overlay');

    fireEvent.pointerDown(overlay, { clientX: 200, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(overlay, { clientX: 600, clientY: 300, pointerId: 1 });
    fireEvent.pointerUp(overlay, { clientX: 600, clientY: 300, pointerId: 1 });

    expect(onMaskCreate).toHaveBeenCalledTimes(1);
    const rect = onMaskCreate.mock.calls[0][0];
    expect(rect.x).toBeCloseTo(0.2, 2);
    expect(rect.y).toBeCloseTo(0.2, 2);
    expect(rect.w).toBeCloseTo(0.4, 2);
    expect(rect.h).toBeCloseTo(0.4, 2);
  });

  it('reports preview target adjustments while dragging the marker', async () => {
    const onPreviewTargetChange = vi.fn();
    render(
      <ScreenView
        frame={new Blob(['x'])}
        preview={{ kind: 'point', target: { x: 0.2, y: 0.2 } }}
        onPreviewTargetChange={onPreviewTargetChange}
      />,
    );
    const marker = await screen.findByTestId('preview-point');
    const overlay = screen.getByTestId('screen-overlay');

    fireEvent.pointerDown(marker, { clientX: 200, clientY: 100, pointerId: 2 });
    fireEvent.pointerMove(overlay, { clientX: 800, clientY: 400, pointerId: 2 });
    fireEvent.pointerUp(overlay, { clientX: 800, clientY: 400, pointerId: 2 });

    expect(onPreviewTargetChange).toHaveBeenCalled();
    const calls = onPreviewTargetChange.mock.calls;
    const target = calls[calls.length - 1]?.[0];
    expect(target.x).toBeCloseTo(0.8, 2);
    expect(target.y).toBeCloseTo(0.8, 2);
  });
});
