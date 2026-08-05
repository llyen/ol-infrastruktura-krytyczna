import { NavLink, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { formatNumber, frameTime } from '@/data/model';
import { useAuth } from '@/hooks/AuthContext';
import { useScenario } from '@/hooks/ScenarioContext';
import { USER_ROLES, type UserRole } from '@/services/workflow';
import { Button } from '@/components/ui';

const NAV = [
  { to: '/', label: 'Symulacja awarii' },
  { to: '/obraz', label: 'Obraz bieżący' },
  { to: '/meldunek', label: 'Meldunek operatora' },
  { to: '/rejestr', label: 'Rejestr IK / SPO-10' },
  { to: '/wzmocnienia', label: 'Plan wzmocnień' },
];

const REGIONAL_ROLES: UserRole[] = ['wojewoda / WCZK'];
const OPERATOR_ROLES: UserRole[] = ['operator IK'];

const timeFormat = new Intl.DateTimeFormat('pl-PL', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

/**
 * Pasek czasu kaskady powodziowej.
 *
 * Domyślnie chwila idzie z zegara ściennego, więc aplikacja wygląda jak
 * podgląd na żywo o dowolnej porze. Suwak przełącza w tryb ręczny — potrzebny,
 * gdy prowadzący chce zatrzymać się na konkretnej godzinie propagacji.
 */
function TimeScrubber() {
  const { index, frame, setFrame, live, setLive } = useScenario();
  if (!index) return null;
  const frames = index.scene.floodFrames;
  const count = frames.length;
  const failed = frames[frame]?.length ?? 0;
  const hour = frame * index.scene.meta.frameHours;
  const moment = frameTime(index.scene.meta, frame);
  const alarm = failed > 200;

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-100 px-5 py-2.5">
      <button
        type="button"
        onClick={() => setLive(!live)}
        className={`flex w-32 items-center justify-center gap-2 rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors ${
          live
            ? 'bg-red-50 text-red-700 ring-1 ring-red-600/40'
            : 'bg-slate-50 text-slate-700 ring-1 ring-slate-300 hover:bg-slate-200'
        }`}
        title={
          live
            ? 'Chwila scenariusza idzie z zegara. Kliknij, żeby zatrzymać na tej godzinie.'
            : 'Wróć do podglądu na żywo'
        }
      >
        {live ? (
          <>
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-red-50" />
            </span>
            NA ŻYWO
          </>
        ) : (
          '⏸ Zatrzymane'
        )}
      </button>
      <div className="flex min-w-[280px] flex-1 items-center gap-3">
        <input
          type="range"
          min={0}
          max={count - 1}
          value={frame}
          onChange={(e) => setFrame(Number(e.target.value))}
          className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-gov"
          aria-label="Godzina scenariusza powodziowego"
        />
        <span
          className={`min-w-[150px] rounded-md px-2 py-1 text-center text-xs font-semibold tabular-nums ${
            alarm ? 'bg-red-50 text-red-700' : 'bg-gov/15 text-gov'
          }`}
        >
          {timeFormat.format(moment)} · H+{formatNumber(hour)}
        </span>
      </div>
      <span className="hidden text-[11px] text-slate-500 lg:inline">
        {formatNumber(failed)} obiektów niedziałających
      </span>
      {!live && (
        <Button variant="ghost" onClick={() => setLive(true)} title="Wróć do podglądu na żywo">
          ⟲ Na żywo
        </Button>
      )}
    </div>
  );
}

function RolePicker() {
  const { actor, setRole, setVoivodeship, setOperator, index } = useScenario();
  const operators = index?.scene.operators ?? [];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        value={actor.role}
        onChange={(e) => setRole(e.target.value as UserRole)}
        className="rounded-lg bg-slate-50 px-2 py-1 text-xs text-slate-900 ring-1 ring-slate-300"
        aria-label="Rola użytkownika"
      >
        {USER_ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      {REGIONAL_ROLES.includes(actor.role) && (
        <select
          value={actor.voivodeshipCode}
          onChange={(e) => setVoivodeship(e.target.value)}
          className="rounded-lg bg-slate-50 px-2 py-1 text-xs text-slate-900 ring-1 ring-slate-300"
          aria-label="Województwo"
        >
          <option value="">— cały kraj —</option>
          {(index?.scene.voivodeships ?? []).map((v) => (
            <option key={v.code} value={v.code}>
              {v.name}
            </option>
          ))}
        </select>
      )}
      {OPERATOR_ROLES.includes(actor.role) && (
        <select
          value={actor.operatorName}
          onChange={(e) => setOperator(e.target.value)}
          className="max-w-[220px] rounded-lg bg-slate-50 px-2 py-1 text-xs text-slate-900 ring-1 ring-slate-300"
          aria-label="Operator"
        >
          <option value="">— wskaż operatora —</option>
          {operators.map((o) => (
            <option key={o.name} value={o.name}>
              {o.name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

/** Przełącznik trybu terenowego — meldunki idą do kolejki synchronizacji. */
function OfflineToggle() {
  const { offline, setOffline, actor } = useScenario();
  if (actor.role !== 'operator IK') return null;
  return (
    <button
      type="button"
      onClick={() => setOffline(!offline)}
      className={`rounded-lg px-2.5 py-1 text-xs font-medium ring-1 transition-colors ${
        offline
          ? 'bg-amber-50 text-amber-700 ring-amber-600/40'
          : 'bg-slate-50 text-slate-500 ring-slate-300 hover:text-slate-900'
      }`}
      title="Tryb terenowy: meldunek zapisuje się lokalnie z identyfikatorem synchronizacji"
    >
      {offline ? '📴 Tryb terenowy' : '📶 Online'}
    </button>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { signOut, user } = useAuth();
  const { writebackError, offline, actor } = useScenario();
  const location = useLocation();
  const active = NAV.find((n) => n.to === location.pathname)?.label ?? '';

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="h-1 w-full bg-gov" />
      <header className="border-b border-slate-200 bg-gradient-to-r from-white via-white to-slate-100">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gov/15 text-gov ring-1 ring-gov/40">
              <span className="text-base font-bold">⚡</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-wide text-slate-900">
                Symulator kaskad · infrastruktura krytyczna
              </h1>
              <p className="text-[11px] text-slate-500">
                Zależności między systemami i skutki awarii · demonstracja
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <OfflineToggle />
            <RolePicker />
            <span className="hidden text-xs text-slate-500 sm:inline">
              {user?.name ?? user?.email ?? ''}
            </span>
            <Button variant="ghost" onClick={() => void signOut()}>
              Wyloguj
            </Button>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-4">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'border-gov text-gov'
                    : 'border-transparent text-slate-500 hover:text-slate-900'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <TimeScrubber />

      {actor.role === 'operator IK' && !actor.operatorName && (
        <div className="border-b border-gov/30 bg-gov/10 px-5 py-2 text-xs text-gov-dark">
          Wskaż operatora w pasku u góry. Rola „operator IK" widzi wyłącznie własne obiekty i nie
          ma dostępu do grafu zależności innych podmiotów.
        </div>
      )}

      {offline && (
        <div className="border-b border-amber-300 bg-amber-50 px-5 py-2 text-xs text-amber-700">
          Tryb terenowy. Meldunek zapisuje się z identyfikatorem synchronizacji i trafi do bazy po
          odzyskaniu łączności. Powtórzona wysyłka tej samej paczki nie utworzy drugiego meldunku.
        </div>
      )}

      {writebackError && (
        <div className="border-b border-amber-300 bg-amber-50 px-5 py-2 text-xs text-amber-700">
          Zapis do bazy aplikacji jest niedostępny ({writebackError}). Decyzje zapisują się lokalnie
          w sesji przeglądarki.
        </div>
      )}

      <main className="mx-auto max-w-[1500px] px-5 py-5">
        <p className="mb-3 text-[11px] uppercase tracking-widest text-slate-400">{active}</p>
        {children}
      </main>

      <footer className="border-t border-slate-200 px-5 py-3 text-[11px] text-slate-400">
        Dane są w całości syntetyczne. Obiekty infrastruktury, operatorzy i zależności to rekordy
        wygenerowane — żaden z nich nie odpowiada rzeczywistemu obiektowi. Progi propagacji, klasy
        krytyczności i ścieżka decyzyjna są konstrukcją demonstracyjną.
      </footer>
    </div>
  );
}
