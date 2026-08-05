import { useEffect, useMemo, type ReactNode } from 'react';

import { formatNumber } from '@/data/model';

/* ------------------------------------------------------------------ */
/* Podstawowe elementy                                                 */
/* ------------------------------------------------------------------ */

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = '',
  tone = 'default',
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  tone?: 'default' | 'alert' | 'accent';
}) {
  const ring =
    tone === 'alert'
      ? 'ring-red-600/30'
      : tone === 'accent'
        ? 'ring-gov/30'
        : 'ring-slate-300';
  return (
    <section
      className={`rounded-xl bg-white ring-1 ${ring} shadow-lg backdrop-blur-sm ${className}`}
    >
      {(title || right) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-4 py-3">
          <div>
            {title && (
              <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-900">
                {title}
              </h2>
            )}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Button({
  children,
  onClick,
  variant = 'default',
  disabled,
  type = 'button',
  className = '',
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  disabled?: boolean;
  type?: 'button' | 'submit';
  className?: string;
  title?: string;
}) {
  const styles = {
    default: 'bg-slate-50 text-slate-900 ring-1 ring-slate-300 hover:bg-slate-200',
    primary: 'bg-gov text-white font-semibold hover:bg-gov',
    danger: 'bg-red-600 text-white font-semibold hover:bg-red-50',
    ghost: 'text-slate-700 hover:bg-slate-50',
  }[variant];
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Badge({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${className}`}
    >
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export const inputClass =
  'w-full rounded-lg border-0 bg-slate-50 px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-300 placeholder:text-slate-500 focus:ring-2 focus:ring-gov focus:outline-none';

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDone, 4200);
    return () => clearTimeout(t);
  }, [message, onDone]);
  if (!message) return null;
  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-gov px-5 py-3 text-sm font-medium text-white shadow-2xl">
      {message}
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  wide,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-6 backdrop-blur-sm">
      <div
        className={`w-full ${wide ? 'max-w-4xl' : 'max-w-2xl'} rounded-2xl bg-white ring-1 ring-slate-200 shadow-2xl`}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-900">{title}</h3>
          <Button variant="ghost" onClick={onClose}>
            Zamknij
          </Button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Wskazniki                                                           */
/* ------------------------------------------------------------------ */

export function KpiCard({
  label,
  value,
  prev,
  unit,
  hint,
  higherIsWorse = true,
  spark,
  emphasis,
}: {
  label: string;
  value: number;
  prev?: number | null;
  unit?: string;
  hint?: string;
  higherIsWorse?: boolean;
  spark?: number[];
  emphasis?: boolean;
}) {
  const delta = prev === null || prev === undefined ? null : Math.round((value - prev) * 10) / 10;
  const worse = delta === null ? false : higherIsWorse ? delta > 0 : delta < 0;
  const better = delta === null ? false : higherIsWorse ? delta < 0 : delta > 0;
  return (
    <div
      className={`group relative overflow-hidden rounded-xl bg-white p-4 ring-1 transition-shadow ${
        emphasis ? 'ring-gov/50 shadow-lg' : 'ring-slate-300'
      }`}
      title={hint}
    >
      <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums text-slate-900">
          {formatNumber(value)}
          {unit ?? ''}
        </span>
        {delta !== null && delta !== 0 && (
          <span
            className={`text-xs font-medium tabular-nums ${
              worse ? 'text-red-700' : better ? 'text-emerald-700' : 'text-slate-500'
            }`}
          >
            {delta > 0 ? '▲' : '▼'} {formatNumber(Math.abs(delta))}
          </span>
        )}
      </div>
      {spark && spark.length > 1 && (
        <div className="mt-2">
          <Sparkline values={spark} height={26} />
        </div>
      )}
      {hint && (
        <p className="pointer-events-none mt-1 line-clamp-2 text-[11px] leading-snug text-slate-500">
          {hint}
        </p>
      )}
    </div>
  );
}

export function Sparkline({
  values,
  height = 32,
  marker,
  color = '#0052a5',
}: {
  values: number[];
  height?: number;
  marker?: number;
  color?: string;
}) {
  const { path, area, points } = useMemo(() => {
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const span = max - min || 1;
    const pts = values.map((v, i) => ({
      x: (i / Math.max(values.length - 1, 1)) * 100,
      y: 100 - ((v - min) / span) * 100,
    }));
    const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
    return { path: d, area: `${d} L100,100 L0,100 Z`, points: pts };
  }, [values]);
  const m = marker !== undefined ? points[marker] : undefined;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} className="w-full">
      <path d={area} fill={color} opacity={0.14} />
      <path d={path} fill="none" stroke={color} strokeWidth={2.5} vectorEffect="non-scaling-stroke" />
      {m && <circle cx={m.x} cy={m.y} r={3} fill={color} stroke="#ffffff" strokeWidth={1.5} />}
    </svg>
  );
}

export function BarList({
  rows,
  color = '#0052a5',
  unit = '',
}: {
  rows: { label: string; value: number; hint?: string }[];
  color?: string;
  unit?: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} title={r.hint}>
          <div className="flex items-baseline justify-between text-xs">
            <span className="truncate text-slate-700">{r.label}</span>
            <span className="ml-2 tabular-nums text-slate-500">
              {formatNumber(Math.round(r.value * 10) / 10)}
              {unit}
            </span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-50">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${(r.value / max) * 100}%`, background: color }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Wykres slupkowy przebiegu w czasie z zaznaczonym dniem biezacym. */
export function TimelineBars({
  values,
  labels,
  activeIndex,
  onSelect,
  height = 60,
  colorFor,
}: {
  values: number[];
  labels: string[];
  activeIndex: number;
  onSelect?: (i: number) => void;
  height?: number;
  colorFor?: (v: number) => string;
}) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex items-end gap-1" style={{ height }}>
      {values.map((v, i) => (
        <button
          key={labels[i]}
          type="button"
          onClick={() => onSelect?.(i)}
          title={`${labels[i]}: ${formatNumber(v)}`}
          className="group relative flex-1 rounded-t transition-all"
          style={{
            height: `${Math.max((v / max) * 100, 3)}%`,
            background: colorFor ? colorFor(v) : '#00417f',
            opacity: i === activeIndex ? 1 : 0.45,
            outline: i === activeIndex ? '1px solid rgba(34,211,238,0.9)' : 'none',
          }}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Mapa                                                                */
/* ------------------------------------------------------------------ */

// Mapa mieszka w osobnym pliku - ma wlasny stan widoku i obsluge zdarzen
// wskaznika, wiec nie pasuje do zbioru bezstanowych elementow tego modulu.
export { CountryMap } from './CountryMap';
export type { MapPoint, MapPath, CountryMapProps } from './CountryMap';


export function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

export function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
