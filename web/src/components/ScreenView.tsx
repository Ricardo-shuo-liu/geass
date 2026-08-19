import { useEffect, useRef } from 'react';

export function ScreenView({ frame }: { frame: Blob | null }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<Blob | null>(null);
  frameRef.current = frame;

  useEffect(() => {
    let disposed = false;
    let bitmap: ImageBitmap | null = null;

    async function draw() {
      const canvas = canvasRef.current;
      const blob = frameRef.current;
      if (!canvas || !blob) return;
      bitmap = await createImageBitmap(blob);
      if (disposed) {
        bitmap.close();
        return;
      }
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      bitmap = null;
    }

    draw().catch(() => {});
    return () => {
      disposed = true;
      if (bitmap) bitmap.close();
    };
  }, [frame]);

  if (!frame) {
    return (
      <div className="screen-placeholder">
        <span className="screen-placeholder-dot" />
        <span>CONNECTING</span>
      </div>
    );
  }
  return <canvas ref={canvasRef} className="screen-canvas" />;
}
