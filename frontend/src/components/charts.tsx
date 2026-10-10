import { useEffect, useRef, useState, type ReactNode } from 'react';

/** Width of a container, kept current with ResizeObserver so SVG text stays 1:1 with CSS pixels. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export interface Pt {
  x: number;
  y: number;
}
export interface Series {
  key: string;
  label: string;
  points: Pt[];
  color: string;
  dashed?: boolean;
}
export interface Marker {
  x: number;
  y: number;
  label: string;
}

interface LineChartProps {
  series: Series[];
  x: { domain: [number, number]; format: (v: number) => string; ticks: number[]; label: string };
  y: { domain: [number, number]; format: (v: number) => string; ticks: number[]; label: string };
  markers?: Marker[];
  /** A vertical rule pinned at this x (e.g. the slider position). */
  pinX?: number;
  height?: number;
  /** Tooltip body for the hovered index of the first series. */
  tooltip: (i: number) => ReactNode;
  ariaLabel: string;
}

const PAD = { top: 12, right: 16, bottom: 40, left: 62 };

/** Line chart with a crosshair + tooltip that snaps to the nearest point of the first series. */
export function LineChart({ series, x, y, markers = [], pinX, height = 280, tooltip, ariaLabel }: LineChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const w = Math.max(0, width - PAD.left - PAD.right);
  const h = height - PAD.top - PAD.bottom;
  const sx = (v: number) => PAD.left + ((v - x.domain[0]) / (x.domain[1] - x.domain[0])) * w;
  const sy = (v: number) => PAD.top + h - ((v - y.domain[0]) / (y.domain[1] - y.domain[0])) * h;
  const clampY = (v: number) => Math.min(y.domain[1], Math.max(y.domain[0], v));

  const paths = series.map((s) => ({
    ...s,
    d: s.points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(clampY(p.y)).toFixed(1)}`).join(''),
  }));

  const primary = series[0]?.points ?? [];
  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const vx = x.domain[0] + ((e.clientX - box.left) / box.width) * (x.domain[1] - x.domain[0]);
    let best = 0;
    primary.forEach((p, i) => {
      if (Math.abs(p.x - vx) < Math.abs(primary[best].x - vx)) best = i;
    });
    setHover(primary.length ? best : null);
  };
  const hp = hover != null ? primary[hover] : null;
  const tipLeft = hp ? sx(hp.x) : 0;

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel} className="block overflow-visible">
          {y.ticks.map((t) => (
            <g key={`y${t}`}>
              <line x1={PAD.left} x2={PAD.left + w} y1={sy(t)} y2={sy(t)} style={{ stroke: 'var(--line)', strokeWidth: 1 }} />
              <text x={PAD.left - 10} y={sy(t)} dy="0.32em" textAnchor="end" style={{ fill: 'var(--muted)', font: "500 11px 'DM Sans', sans-serif" }}>
                {y.format(t)}
              </text>
            </g>
          ))}
          {x.ticks.map((t) => (
            <text key={`x${t}`} x={sx(t)} y={PAD.top + h + 18} textAnchor="middle" style={{ fill: 'var(--muted)', font: "500 11px 'DM Sans', sans-serif" }}>
              {x.format(t)}
            </text>
          ))}
          <text x={PAD.left + w / 2} y={height - 4} textAnchor="middle" style={{ fill: 'var(--muted-2)', font: "500 12px 'DM Sans', sans-serif" }}>
            {x.label}
          </text>
          <text
            transform={`translate(12 ${PAD.top + h / 2}) rotate(-90)`}
            textAnchor="middle"
            style={{ fill: 'var(--muted-2)', font: "500 12px 'DM Sans', sans-serif" }}
          >
            {y.label}
          </text>

          {pinX != null && <line x1={sx(pinX)} x2={sx(pinX)} y1={PAD.top} y2={PAD.top + h} style={{ stroke: 'var(--brand)', strokeWidth: 1.5, strokeDasharray: '4 4' }} />}

          {paths.map((s) => (
            <path
              key={s.key}
              d={s.d}
              style={{ fill: 'none', stroke: s.color, strokeWidth: 2, strokeLinejoin: 'round', strokeLinecap: 'round', strokeDasharray: s.dashed ? '6 5' : undefined }}
            />
          ))}

          {markers.map((m) => (
            <g key={m.label}>
              <circle cx={sx(m.x)} cy={sy(clampY(m.y))} r={6} style={{ fill: 'var(--brand)', stroke: 'var(--card)', strokeWidth: 2 }} />
              <text x={sx(m.x) + 10} y={sy(clampY(m.y)) - 8} style={{ fill: 'var(--ink)', font: "700 11px 'DM Sans', sans-serif" }}>
                {m.label}
              </text>
            </g>
          ))}

          {hp && (
            <g pointerEvents="none">
              <line x1={sx(hp.x)} x2={sx(hp.x)} y1={PAD.top} y2={PAD.top + h} style={{ stroke: 'var(--muted)', strokeWidth: 1 }} />
              {series.map((s) => {
                const p = s.points[hover!];
                return p ? <circle key={s.key} cx={sx(p.x)} cy={sy(clampY(p.y))} r={4.5} style={{ fill: s.color, stroke: 'var(--card)', strokeWidth: 2 }} /> : null;
              })}
            </g>
          )}

          <rect x={PAD.left} y={PAD.top} width={w} height={h} fill="transparent" onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
        </svg>
      )}
      {hp && (
        <div
          className="pointer-events-none absolute z-10 min-w-[160px] rounded-xl bg-card px-3 py-2 text-xs shadow-card"
          style={{ top: PAD.top, left: tipLeft, transform: `translateX(${tipLeft > width / 2 ? 'calc(-100% - 12px)' : '12px'})`, border: '1px solid var(--line)' }}
        >
          {tooltip(hover!)}
        </div>
      )}
    </div>
  );
}

/** Legend row for ≥ 2 series; the swatch mirrors the line style so identity isn't colour-only. */
export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs font-medium text-muted2">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-2">
          <svg width="22" height="6" aria-hidden="true">
            <line x1="1" x2="21" y1="3" y2="3" style={{ stroke: it.color, strokeWidth: 2, strokeLinecap: 'round', strokeDasharray: it.dashed ? '5 4' : undefined }} />
          </svg>
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** Horizontal bar with the value in text ink beside it. */
export function HBar({ label, value, max, display, title, labelWidth = '38%' }: { label: ReactNode; value: number; max: number; display: string; title?: string; labelWidth?: string }) {
  const width = max > 0 ? Math.max(1.5, (value / max) * 100) : 0;
  return (
    <div className="grid items-center gap-3" style={{ gridTemplateColumns: `minmax(110px, ${labelWidth}) 1fr 64px` }} title={title}>
      <div className="truncate text-[13px] font-medium">{label}</div>
      <div className="h-2.5 rounded-[4px] bg-bg">
        <div className="h-2.5 rounded-[4px] bg-brand transition-[width] duration-500" style={{ width: `${width}%` }} />
      </div>
      <div className="text-right font-mono text-[12px] text-muted2">{display}</div>
    </div>
  );
}
