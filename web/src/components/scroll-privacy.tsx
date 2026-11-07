import { useLayoutEffect, useRef } from 'react';
import { t } from '../i18n/index.mjs';

// Three separable box passes approximate the 48px Gaussian blur. Work on a small
// bitmap so the moving strip never needs a full-resolution CSS filter surface.
function blur(source: Float32Array, target: Float32Array, width: number, height: number, radius: number, vertical: boolean) {
  const length = vertical ? height : width, lines = vertical ? width : height;
  const step = vertical ? width * 4 : 4, divisor = radius * 2 + 1;
  for (let line = 0; line < lines; line++) for (let channel = 0; channel < 4; channel++) {
    const start = (vertical ? line * 4 : line * width * 4) + channel;
    let sum = source[start] * (radius + 1);
    for (let i = 1; i <= radius; i++) sum += source[start + Math.min(i, length - 1) * step];
    for (let i = 0; i < length; i++) {
      target[start + i * step] = sum / divisor;
      sum += source[start + Math.min(i + radius + 1, length - 1) * step]
        - source[start + Math.max(i - radius, 0) * step];
    }
  }
}

function paint(canvas: HTMLCanvasElement, image: HTMLImageElement, displayHeight: number) {
  if (!image.complete || !image.naturalWidth || displayHeight < 2) return;
  const scale = Math.min(1, 192 / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  canvas.width = width; canvas.height = height;
  const context = canvas.getContext('2d')!;
  context.drawImage(image, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height);
  const source = new Float32Array(pixels.data.length), target = new Float32Array(source.length);
  // Blur premultiplied colors, including alpha, without dark transparent edges.
  for (let i = 0; i < source.length; i += 4) {
    const alpha = pixels.data[i + 3] / 255;
    for (let channel = 0; channel < 3; channel++) source[i + channel] = pixels.data[i + channel] * alpha;
    source[i + 3] = pixels.data[i + 3];
  }
  const sigma = 48 * height / displayHeight;
  let lower = Math.floor(Math.sqrt(4 * sigma * sigma + 1));
  if (lower % 2 === 0) lower--;
  const count = Math.round((12 * sigma * sigma - 3 * lower * lower - 12 * lower - 9) / (-4 * lower - 4));
  for (let pass = 0; pass < 3; pass++) {
    const radius = ((pass < count ? lower : lower + 2) - 1) / 2;
    blur(source, target, width, height, radius, false);
    blur(target, source, width, height, radius, true);
  }
  for (let i = 0; i < source.length; i += 4) {
    const alpha = source[i + 3];
    for (let channel = 0; channel < 3; channel++) pixels.data[i + channel] = alpha ? source[i + channel] * 255 / alpha : 0;
    pixels.data[i + 3] = alpha;
  }
  context.putImageData(pixels, 0, 0);
}

/** Keep the decoded original for reveal and geometry; only the blurred bitmap is visible. */
export function ScrollPrivacyImage({ src, height, blurred, onLoad, onError }: {
  src: string; height: number; blurred: boolean;
  onLoad: (image: HTMLImageElement) => void; onError: () => void;
}) {
  const image = useRef<HTMLImageElement>(null), preview = useRef<HTMLCanvasElement>(null);
  const draw = () => { if (blurred && image.current && preview.current) paint(preview.current, image.current, height); };
  useLayoutEffect(draw, [blurred, height]);
  return <>
    <img ref={image} alt={t('生成的图片')} draggable={false} src={src} decoding="async" hidden={blurred}
      onLoad={event => { draw(); onLoad(event.currentTarget); }} onError={onError} />
    {blurred && <canvas ref={preview} className="roam-scroll-blur" aria-hidden="true" />}
  </>;
}
