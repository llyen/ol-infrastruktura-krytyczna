import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  indexScene,
  liveFrameIndex,
  msToNextFrame,
  type Scene,
  type SceneIndex,
} from '@/data/model';
import { useAuth } from '@/hooks/AuthContext';
import {
  listCooperationActions,
  listFuelRequests,
  listHardeningDecisions,
  listOperatorReports,
  listScenarios,
  type Actor,
  type CooperationActionRecord,
  type ExerciseScenarioRecord,
  type FuelRequestRecord,
  type HardeningDecisionRecord,
  type OperatorReportRecord,
  type UserRole,
} from '@/services/workflow';

interface ScenarioValue {
  index: SceneIndex | null;
  loading: boolean;
  error: string | null;
  /** Klatka kaskady powodziowej pokazywana na ekranie „Obraz bieżący". */
  frame: number;
  setFrame: (i: number) => void;
  /** Czy klatka jest wyliczana z zegara ściennego. */
  live: boolean;
  setLive: (v: boolean) => void;
  actor: Actor;
  setRole: (role: UserRole) => void;
  setVoivodeship: (code: string) => void;
  setOperator: (name: string) => void;
  /** Tryb terenowy — meldunki trafiają do kolejki synchronizacji. */
  offline: boolean;
  setOffline: (v: boolean) => void;
  scenarios: ExerciseScenarioRecord[];
  fuelRequests: FuelRequestRecord[];
  reports: OperatorReportRecord[];
  cooperation: CooperationActionRecord[];
  hardening: HardeningDecisionRecord[];
  refresh: () => Promise<void>;
  writebackError: string | null;
}

const ScenarioContext = createContext<ScenarioValue | undefined>(undefined);

const ROLE_KEY = 'kaskady.role';
const VOIV_KEY = 'kaskady.voivodeship';
const OPERATOR_KEY = 'kaskady.operator';

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [index, setIndex] = useState<SceneIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrameState] = useState(0);
  const [live, setLiveState] = useState(true);
  const [offline, setOffline] = useState(false);
  const [role, setRoleState] = useState<UserRole>(
    () => (localStorage.getItem(ROLE_KEY) as UserRole) || 'RCB',
  );
  const [voivodeship, setVoivodeshipState] = useState(
    () => localStorage.getItem(VOIV_KEY) || '',
  );
  const [operator, setOperatorState] = useState(
    () => localStorage.getItem(OPERATOR_KEY) || '',
  );
  const [scenarios, setScenarios] = useState<ExerciseScenarioRecord[]>([]);
  const [fuelRequests, setFuelRequests] = useState<FuelRequestRecord[]>([]);
  const [reports, setReports] = useState<OperatorReportRecord[]>([]);
  const [cooperation, setCooperation] = useState<CooperationActionRecord[]>([]);
  const [hardening, setHardening] = useState<HardeningDecisionRecord[]>([]);
  const [writebackError, setWritebackError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${import.meta.env.BASE_URL}data/scene.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`Nie udało się wczytać sceny (HTTP ${r.status}).`);
        return r.json() as Promise<Scene>;
      })
      .then((scene) => {
        if (cancelled) return;
        const idx = indexScene(scene);
        setIndex(idx);
        setFrameState(liveFrameIndex(idx.scene.floodFrames.length));
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Zegar sceny.
   *
   * Klatka jest **liczona z bieżącego czasu**, a nie zwiększana licznikiem.
   * Dzięki temu przebieg nie rozjeżdża się, gdy przeglądarka uśpi zakładkę,
   * a odświeżenie strony nie cofa demonstracji do początku. Odstęp liczymy
   * do najbliższego przeskoku, więc zmiana następuje równo z zegarem.
   */
  useEffect(() => {
    if (!live || !index) return;
    const count = index.scene.floodFrames.length;
    let stopped = false;

    const tick = () => {
      if (stopped) return;
      setFrameState(liveFrameIndex(count));
      timer.current = window.setTimeout(tick, msToNextFrame(count) + 50);
    };
    setFrameState(liveFrameIndex(count));
    timer.current = window.setTimeout(tick, msToNextFrame(count) + 50);

    return () => {
      stopped = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [live, index]);

  const refresh = useCallback(async () => {
    try {
      const [s, f, r, c, h] = await Promise.all([
        listScenarios(),
        listFuelRequests(),
        listOperatorReports(),
        listCooperationActions(),
        listHardeningDecisions(),
      ]);
      setScenarios(s);
      setFuelRequests(f);
      setReports(r);
      setCooperation(c);
      setHardening(h);
      setWritebackError(null);
    } catch (e: unknown) {
      setWritebackError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setFrame = useCallback((i: number) => {
    setLiveState(false);
    setFrameState(i);
  }, []);

  const setLive = useCallback(
    (v: boolean) => {
      setLiveState(v);
      if (v && index) setFrameState(liveFrameIndex(index.scene.floodFrames.length));
    },
    [index],
  );

  const setRole = useCallback((r: UserRole) => {
    setRoleState(r);
    localStorage.setItem(ROLE_KEY, r);
  }, []);

  const setVoivodeship = useCallback((code: string) => {
    setVoivodeshipState(code);
    localStorage.setItem(VOIV_KEY, code);
  }, []);

  const setOperator = useCallback((name: string) => {
    setOperatorState(name);
    localStorage.setItem(OPERATOR_KEY, name);
  }, []);

  const actor: Actor = useMemo(
    () => ({
      id: user?.id ?? 'local-user',
      name: user?.name ?? user?.email ?? 'Użytkownik demonstracyjny',
      role,
      voivodeshipCode: voivodeship,
      operatorName: operator,
    }),
    [user, role, voivodeship, operator],
  );

  const value: ScenarioValue = useMemo(
    () => ({
      index,
      loading,
      error,
      frame,
      setFrame,
      live,
      setLive,
      actor,
      setRole,
      setVoivodeship,
      setOperator,
      offline,
      setOffline,
      scenarios,
      fuelRequests,
      reports,
      cooperation,
      hardening,
      refresh,
      writebackError,
    }),
    [
      index,
      loading,
      error,
      frame,
      setFrame,
      live,
      setLive,
      actor,
      setRole,
      setVoivodeship,
      setOperator,
      offline,
      scenarios,
      fuelRequests,
      reports,
      cooperation,
      hardening,
      refresh,
      writebackError,
    ],
  );

  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
}

export function useScenario(): ScenarioValue {
  const ctx = useContext(ScenarioContext);
  if (!ctx) throw new Error('useScenario musi być użyte wewnątrz ScenarioProvider');
  return ctx;
}
