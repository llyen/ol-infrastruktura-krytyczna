import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { REGIONS } from '@/data/poland';

/* ------------------------------------------------------------------ */
/* Rzut                                                                */
/* ------------------------------------------------------------------ */

/**
 * Musi byc identyczne z BOUNDS w `data/model.ts` oraz w generatorze
 * `tools/build_poland_geo.py`, bo granice wojewodztw sa wstepnie rzutowane
 * na te sama siatke. Rozjazd tych trzech miejsc przesunie punkty wzgledem
 * granic - to jedyny sposob, w jaki ta mapa moze sie zepsuc po cichu.
 */
const BOUNDS = { minLat: 49.0, maxLat: 54.9, minLon: 14.1, maxLon: 24.2 };

/** Rzut rownoprostokatny na kwadrat 0..100. Dla Polski znieksztalcenie jest pomijalne. */
function toXY(lat: number, lon: number): { x: number; y: number } {
  return {
    x: ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * 100,
    y: 100 - ((lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) * 100,
  };
}

/** Sprowadza nazwe wojewodztwa do postaci bez znakow diakrytycznych. */
function foldName(text: string): string {
  return text
    .replace(/ł/g, 'l')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

/* ------------------------------------------------------------------ */
/* Widok - przyblizanie i przesuwanie                                  */
/* ------------------------------------------------------------------ */

interface View {
  x: number;
  y: number;
  w: number;
}

const FULL: View = { x: 0, y: 0, w: 100 };

/** 14x to granica, przy ktorej upraszczanie granic zaczyna byc widoczne. */
const MAX_ZOOM = 14;
const MIN_W = 100 / MAX_ZOOM;

function clampView(next: View): View {
  const w = Math.min(100, Math.max(MIN_W, next.w));
  const limit = 100 - w;
  return {
    w,
    x: Math.min(limit, Math.max(0, next.x)),
    y: Math.min(limit, Math.max(0, next.y)),
  };
}

/** Przyblizenie wokol wskazanego punktu - punkt pod kursorem zostaje w miejscu. */
function zoomAt(view: View, factor: number, ax: number, ay: number): View {
  const w = Math.min(100, Math.max(MIN_W, view.w / factor));
  const ratio = w / view.w;
  return clampView({
    w,
    x: ax - (ax - view.x) * ratio,
    y: ay - (ay - view.y) * ratio,
  });
}

/* ------------------------------------------------------------------ */
/* Typy publiczne                                                      */
/* ------------------------------------------------------------------ */

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  value: number;
  label: string;
  detail?: string;
  alarm?: boolean;
}

export interface MapPath {
  id: string;
  points: number[][];
  color: string;
}

export interface CountryMapProps {
  points: MapPoint[];
  anchors?: MapPoint[];
  onSelect?: (id: string) => void;
  selectedId?: string | null;
  height?: number;
  /** Skala barw jest wstrzykiwana, bo ta sama mapa sluzy do roznych wielkosci. */
  colorFor: (value: number) => string;
  legend?: { label: string; value: number }[];
  paths?: MapPath[];
  /** Podswietlenie wojewodztwa, np. objetego zdarzeniem. Nazwy malymi literami. */
  highlightRegions?: string[];
}

/* ------------------------------------------------------------------ */
/* Mapa                                                                */
/* ------------------------------------------------------------------ */

/**
 * Mapa Polski z granicami wojewodztw, przybliżaniem i przesuwaniem.
 *
 * Sterowanie: kolko myszy lub gest szczypania przybliza w miejscu kursora,
 * przeciagniecie przesuwa, dwuklik przybliza dwukrotnie, klawisze strzalek
 * przesuwaja, `+` i `-` zmieniaja przyblizenie, `0` wraca do pelnego widoku.
 *
 * Wielkosci znacznikow, grubosci linii i wielkosci napisow sa dzielone przez
 * przyblizenie, dzieki czemu na ekranie zostaja stale - przybliza sie mapa,
 * a nie symbole.
 */
export function CountryMap({
  points,
  anchors = [],
  onSelect,
  selectedId,
  height = 420,
  colorFor,
  legend,
  paths,
  highlightRegions,
}: CountryMapProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState<View>(FULL);
  const [hover, setHover] = useState<MapPoint | null>(null);
  const [dragging, setDragging] = useState(false);

  // Wspolrzedne uzytkownika sa liczone przez macierz SVG, bo przy
  // preserveAspectRatio="meet" plotno bywa oblamowane po bokach i prosty
  // przelicznik z prostokata elementu dawalby przesuniecie.
  const toUser = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const pt = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: pt.x, y: pt.y };
  }, []);

  // Kolko myszy wymaga nasluchu nieprzezroczystego dla przewijania strony,
  // a React podpina zdarzenie `wheel` jako pasywne.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const anchor = toUser(event.clientX, event.clientY);
      if (!anchor) return;
      const factor = Math.exp(-event.deltaY * 0.0015);
      setView((current) => zoomAt(current, factor, anchor.x, anchor.y));
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, [toUser]);

  const drag = useRef<{ id: number; x: number; y: number; moved: number } | null>(null);

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    const start = toUser(event.clientX, event.clientY);
    if (!start) return;
    drag.current = { id: event.pointerId, x: start.x, y: start.y, moved: 0 };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const state = drag.current;
    if (!state || state.id !== event.pointerId) return;
    const now = toUser(event.clientX, event.clientY);
    if (!now) return;
    const dx = state.x - now.x;
    const dy = state.y - now.y;
    state.moved += Math.abs(dx) + Math.abs(dy);
    setView((current) => clampView({ ...current, x: current.x + dx, y: current.y + dy }));
  };

  const endDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    const state = drag.current;
    if (!state || state.id !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drag.current = null;
    setDragging(false);
  };

  /** Przeciagniecie nie moze uchodzic za wybor punktu pod kursorem. */
  const wasDrag = () => (drag.current?.moved ?? 0) > 0.4;

  const onDoubleClick = (event: React.MouseEvent<SVGSVGElement>) => {
    const anchor = toUser(event.clientX, event.clientY);
    if (!anchor) return;
    setView((current) => zoomAt(current, 2, anchor.x, anchor.y));
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const step = view.w * 0.12;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      setView((c) => clampView({ ...c, x: c.x + move[0], y: c.y + move[1] }));
      return;
    }
    if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      setView((c) => zoomAt(c, 1.5, c.x + c.w / 2, c.y + c.w / 2));
    } else if (event.key === '-' || event.key === '_') {
      event.preventDefault();
      setView((c) => zoomAt(c, 1 / 1.5, c.x + c.w / 2, c.y + c.w / 2));
    } else if (event.key === '0') {
      event.preventDefault();
      setView(FULL);
    }
  };

  const zoomBy = (factor: number) =>
    setView((c) => zoomAt(c, factor, c.x + c.w / 2, c.y + c.w / 2));

  // Skala odwrotna: przy przyblizeniu 4x symbole rysujemy 4x mniejsze
  // w jednostkach mapy, wiec na ekranie maja stala wielkosc.
  const s = view.w / 100;
  const zoom = 100 / view.w;
  // Nazwy wojewodztw w zbiorach demo bywaja bez znakow diakrytycznych,
  // a w granicach sa z nimi - porownujemy wiec po ujednoliceniu.
  const highlighted = useMemo(
    () => new Set((highlightRegions ?? []).map(foldName)),
    [highlightRegions],
  );

  const pathData = useMemo(
    () =>
      (paths ?? []).map((line) => ({
        id: line.id,
        color: line.color,
        d: line.points
          .map((pt, i) => {
            const p = toXY(pt[0], pt[1]);
            return `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`;
          })
          .join(' '),
      })),
    [paths],
  );

  const atFullView = view.w >= 100;

  return (
    <div
      className="relative outline-none"
      style={{ height }}
      tabIndex={0}
      onKeyDown={onKeyDown}
      role="application"
      aria-label="Mapa Polski. Strzalki przesuwaja, plus i minus zmieniaja przyblizenie, zero wraca do pelnego widoku."
    >
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.w}`}
        preserveAspectRatio="xMidYMid meet"
        className="h-full w-full touch-none"
        style={{ cursor: dragging ? 'grabbing' : 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={onDoubleClick}
      >
        <defs>
          <radialGradient id="cm-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#0052a5" stopOpacity="0.20" />
            <stop offset="100%" stopColor="#0052a5" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Tlo rysowane z nadmiarem, zeby przy przesunieciu nie odslonic krawedzi. */}
        <rect x={-50} y={-50} width={200} height={200} fill="#eef2f7" />
        <rect x={-50} y={-50} width={200} height={200} fill="url(#cm-glow)" />

        <g>
          {REGIONS.map((region) => {
            const on = highlighted.has(foldName(region.name));
            return (
              <path
                key={region.name}
                d={region.path}
                fill={on ? 'rgba(14,165,233,0.16)' : 'rgba(30,41,59,0.75)'}
                stroke={on ? '#0052a5' : '#c3ced9'}
                strokeWidth={(on ? 0.28 : 0.16) * s}
                strokeLinejoin="round"
              />
            );
          })}
        </g>

        {/* Etykiety wojewodztw znikaja po przyblizeniu - wtedy prowadza juz
            nazwy punktow, a powtarzanie nazwy regionu tylko zasmieca kadr. */}
        {zoom < 3 && (
          <g pointerEvents="none">
            {REGIONS.map((region) => (
              <text
                key={`l-${region.name}`}
                x={region.cx}
                y={region.cy}
                textAnchor="middle"
                fontSize={1.6 * s}
                fill="#94a3b8"
                className="select-none uppercase"
                style={{ letterSpacing: `${0.12 * s}px` }}
              >
                {region.name}
              </text>
            ))}
          </g>
        )}

        <g pointerEvents="none">
          {pathData.map((line) => (
            <path
              key={line.id}
              d={line.d}
              fill="none"
              stroke={line.color}
              strokeWidth={0.35 * s}
              strokeDasharray={`${1.2 * s} ${0.8 * s}`}
              opacity={0.8}
            />
          ))}
        </g>

        <g>
          {anchors.map((a) => {
            const p = toXY(a.lat, a.lon);
            return (
              <g key={`a-${a.id}`}>
                <rect
                  x={p.x - 1.1 * s}
                  y={p.y - 1.1 * s}
                  width={2.2 * s}
                  height={2.2 * s}
                  fill="none"
                  stroke="#64748b"
                  strokeWidth={0.35 * s}
                  opacity={0.9}
                  onMouseEnter={() => setHover(a)}
                  onMouseLeave={() => setHover(null)}
                />
                {zoom > 1.6 && (
                  <text
                    x={p.x}
                    y={p.y - 2.0 * s}
                    textAnchor="middle"
                    fontSize={1.5 * s}
                    fill="#334155"
                    className="select-none"
                    pointerEvents="none"
                  >
                    {a.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>

        <g>
          {points.map((pt) => {
            const p = toXY(pt.lat, pt.lon);
            const r = (0.5 + Math.min(pt.value, 100) / 28) * s;
            const selected = selectedId === pt.id;
            return (
              <g key={pt.id}>
                {pt.alarm && (
                  <circle cx={p.x} cy={p.y} r={r * 2.4} fill={colorFor(pt.value)} opacity={0.16}>
                    <animate
                      attributeName="opacity"
                      values="0.05;0.28;0.05"
                      dur="2.4s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={r}
                  fill={colorFor(pt.value)}
                  stroke={selected ? '#0f172a' : 'rgba(15,23,42,0.6)'}
                  strokeWidth={(selected ? 0.6 : 0.2) * s}
                  opacity={0.92}
                  onMouseEnter={() => setHover(pt)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => {
                    if (!wasDrag()) onSelect?.(pt.id);
                  }}
                  className="cursor-pointer"
                />
              </g>
            );
          })}
        </g>
      </svg>

      {hover && (
        <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-slate-100 px-3 py-2 text-xs ring-1 ring-slate-200">
          <div className="font-semibold text-slate-900">{hover.label}</div>
          {hover.detail && <div className="mt-0.5 text-slate-500">{hover.detail}</div>}
        </div>
      )}

      <div className="absolute right-2 top-2 flex flex-col overflow-hidden rounded-lg ring-1 ring-slate-200">
        <MapButton label="Przybliż" onClick={() => zoomBy(1.5)} disabled={view.w <= MIN_W + 1e-6}>
          +
        </MapButton>
        <MapButton label="Oddal" onClick={() => zoomBy(1 / 1.5)} disabled={atFullView}>
          −
        </MapButton>
        <MapButton label="Cała Polska" onClick={() => setView(FULL)} disabled={atFullView}>
          ⤢
        </MapButton>
      </div>

      {!atFullView && (
        <div className="pointer-events-none absolute right-2 top-[7.25rem] rounded bg-slate-100 px-1.5 py-0.5 text-[10px] tabular-nums text-slate-600 ring-1 ring-slate-200">
          {zoom.toFixed(1)}×
        </div>
      )}

      {legend && legend.length > 0 && (
        <div className="pointer-events-none absolute bottom-2 right-2 flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-1.5 text-[10px] text-slate-600 ring-1 ring-slate-200">
          {legend.map((l) => (
            <span key={l.label} className="flex items-center gap-1">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: colorFor(l.value) }}
              />
              {l.label}
            </span>
          ))}
        </div>
      )}

      <div className="pointer-events-none absolute bottom-2 left-2 text-[10px] text-slate-400">
        kółko myszy — przybliżenie · przeciągnij — przesuń · dwuklik — przybliż
      </div>
    </div>
  );
}

function MapButton({
  children,
  label,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="h-7 w-7 bg-slate-100 text-sm leading-none text-slate-700 transition hover:bg-slate-50 hover:text-white disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-slate-100"
    >
      {children}
    </button>
  );
}
