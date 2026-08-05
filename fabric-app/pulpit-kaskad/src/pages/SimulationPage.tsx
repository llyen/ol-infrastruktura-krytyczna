import { useCallback, useMemo, useState } from 'react';

import { CountryMap, type MapPoint } from '@/components/CountryMap';
import {
  BarList,
  Button,
  EmptyState,
  Field,
  KpiCard,
  Modal,
  Panel,
  Toast,
  downloadCsv,
  inputClass,
} from '@/components/ui';
import {
  DEFAULT_HORIZON_H,
  effectTree,
  firstHours,
  simulate,
  type CascadeEvent,
  type CascadeResult,
} from '@/data/cascade';
import {
  formatHours,
  formatNumber,
  frameTime,
  groupColor,
  groupLabel,
  shortGminaName,
  shortNodeName,
} from '@/data/model';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  SIMULATION_MODES,
  canSeeDependencyGraph,
  canWrite,
  saveScenario,
  type SimulationMode,
} from '@/services/workflow';

/** Barwy fal propagacji — im dalsza fala, tym chłodniejsza barwa. */
const WAVE_COLORS = ['#d5233f', '#c2410c', '#a16207', '#0369a1', '#4338ca', '#6d28d9'];

function waveColor(wave: number): string {
  return WAVE_COLORS[Math.min(wave, WAVE_COLORS.length - 1)];
}

const SHOCK_HOURS = 6;

export function SimulationPage() {
  const { index, loading, error, frame, actor, refresh } = useScenario();
  const [query, setQuery] = useState('');
  const [seedId, setSeedId] = useState<string>('');
  const [mode, setMode] = useState<SimulationMode>(SIMULATION_MODES[0]);
  const [horizon, setHorizon] = useState(DEFAULT_HORIZON_H);
  const [assumeBackups, setAssumeBackups] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const seeGraph = canSeeDependencyGraph(actor.role);

  /** Podpowiedzi: obiekty o największym zasięgu kaskady, policzone poza aplikacją. */
  const suggestions = useMemo(() => {
    if (!index) return [];
    return index.scene.topCascade.slice(0, 8).map((t) => ({
      id: index.id[t.node],
      name: shortNodeName(index.name[t.node]),
      nodes: t.nodes,
      population: t.population,
    }));
  }, [index]);

  const matches = useMemo(() => {
    if (!index) return [];
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const out: number[] = [];
    for (let i = 0; i < index.count && out.length < 40; i += 1) {
      if (actor.voivodeshipCode && index.voiv[i] !== actor.voivodeshipCode) continue;
      const hay = `${index.id[i]} ${index.name[i]} ${index.operator[i]} ${
        index.gminaNames[index.gmina[i]] ?? ''
      }`.toLowerCase();
      if (hay.includes(q)) out.push(i);
    }
    return out;
  }, [index, query, actor.voivodeshipCode]);

  const seed = useMemo(() => {
    if (!index || !seedId) return null;
    const i = index.byId.get(seedId);
    return i === undefined ? null : i;
  }, [index, seedId]);

  /**
   * Awaria zapowiedziana daje sztabowi dwie godziny wyprzedzenia — obiekt pada
   * później, więc bufory paliwowe zdążą zacząć się liczyć od innej chwili.
   * To jedyna różnica między trybami i celowo jest widoczna w wyniku.
   */
  const result: CascadeResult | null = useMemo(() => {
    if (!index || seed === null) return null;
    const startHour = mode === 'awaria zapowiedziana' ? 2 : 0;
    return simulate(index, {
      seeds: new Map([[seed, startHour]]),
      horizonHours: horizon,
      assumeAllBackupsWork: assumeBackups,
    });
  }, [index, seed, mode, horizon, assumeBackups]);

  const tree = useMemo(() => (result ? effectTree(result) : null), [result]);

  const shock = useMemo(
    () => (result ? firstHours(result, SHOCK_HOURS) : []),
    [result],
  );

  const points: MapPoint[] = useMemo(() => {
    if (!index || !result) return [];
    return result.events.map((e) => ({
      id: index.id[e.node],
      lat: index.lat[e.node],
      lon: index.lon[e.node],
      value: e.wave,
      label: shortNodeName(index.name[e.node]),
      detail: `${groupLabel(index.group[e.node])} · H+${formatNumber(e.failHour, 1)} · fala ${e.wave}`,
      alarm: index.critClass[e.node] === 'K1',
    }));
  }, [index, result]);

  const groupRows = useMemo(() => {
    if (!result) return [];
    return [...result.bySystemGroup.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([g, n]) => ({ label: groupLabel(g), value: n, hint: g }));
  }, [result]);

  const toggle = useCallback((node: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(node)) next.delete(node);
      else next.add(node);
      return next;
    });
  }, []);

  if (loading) return <EmptyState text="Wczytywanie grafu zależności…" />;
  if (error) return <EmptyState text={error} />;
  if (!index) return null;

  const sceneTime = frameTime(index.scene.meta, frame).toISOString();

  const submit = async () => {
    if (!result || seed === null) return;
    const draft = {
      scene_time: sceneTime,
      seed_node_id: index.id[seed],
      seed_node_name: index.name[seed],
      voivodeship_code: index.voiv[seed],
      mode,
      horizon_hours: horizon,
      assume_backups: assumeBackups,
      nodes_failed: result.nodesFailed,
      nodes_secondary: result.nodesSecondary,
      max_wave: result.maxWave,
      affected_gminas: result.affectedGminas.size,
      affected_population: result.affectedPopulation,
      k1_nodes_failed: result.k1Failed,
      first_secondary_hour: result.firstSecondaryHour,
      title,
      note,
    };
    try {
      await saveScenario(draft, actor);
      await refresh();
      setSaveOpen(false);
      setTitle('');
      setNote('');
      setErrors([]);
      setToast('Scenariusz ćwiczebny zapisany. Trafi do rejestru ćwiczeń.');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const exportCsv = () => {
    if (!result) return;
    const head = 'node_id;nazwa;system;gmina;wojewodztwo;fala;godzina;przyczyna;zaleznosc\n';
    const body = result.events
      .map((e) =>
        [
          index.id[e.node],
          index.name[e.node],
          index.systemCode[e.node],
          index.gminaNames[index.gmina[e.node]] ?? index.gmina[e.node],
          index.voivName.get(index.voiv[e.node]) ?? index.voiv[e.node],
          e.wave,
          e.failHour,
          e.causeNode === null ? '' : index.id[e.causeNode],
          e.dependency,
        ].join(';'),
      )
      .join('\n');
    downloadCsv(`kaskada-${seedId}.csv`, head + body);
  };

  const renderBranch = (parent: number | null, depth: number) => {
    const children = tree?.get(parent) ?? [];
    if (!children.length) return null;
    return (
      <ul className={depth === 0 ? 'space-y-1' : 'ml-4 space-y-1 border-l border-slate-200 pl-3'}>
        {children.map((e: CascadeEvent) => {
          const hasChildren = (tree?.get(e.node) ?? []).length > 0;
          const open = expanded.has(e.node);
          return (
            <li key={e.node}>
              <div className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => hasChildren && toggle(e.node)}
                  className={`w-4 text-slate-500 ${hasChildren ? 'hover:text-slate-900' : 'invisible'}`}
                  aria-label={open ? 'Zwiń' : 'Rozwiń'}
                >
                  {open ? '▾' : '▸'}
                </button>
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: waveColor(e.wave) }}
                />
                <span className="truncate font-medium text-slate-900">
                  {shortNodeName(index.name[e.node])}
                </span>
                <span className="shrink-0 text-slate-500">
                  {groupLabel(index.group[e.node])} · H+{formatNumber(e.failHour, 1)}
                </span>
                {e.dependency !== 'seed' && (
                  <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                    {e.dependency}
                  </span>
                )}
                {index.critClass[e.node] === 'K1' && (
                  <span className="shrink-0 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
                    K1
                  </span>
                )}
              </div>
              {open && renderBranch(e.node, depth + 1)}
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <Panel title="Wybierz obiekt" subtitle="Co się stanie, gdy ten obiekt przestanie działać">
          <div className="space-y-3">
            <Field label="Szukaj" hint="Nazwa obiektu, identyfikator, operator lub gmina">
              <input
                className={inputClass}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="np. GPZ, szpital, IK-01-00026"
              />
            </Field>

            {matches.length > 0 && (
              <div className="max-h-64 overflow-y-auto rounded-lg ring-1 ring-slate-200">
                {matches.map((i) => (
                  <button
                    key={index.id[i]}
                    type="button"
                    onClick={() => setSeedId(index.id[i])}
                    className={`block w-full px-3 py-2 text-left text-xs transition-colors ${
                      seedId === index.id[i]
                        ? 'bg-gov/15 text-gov'
                        : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    <span className="block truncate font-medium">
                      {shortNodeName(index.name[i])}
                    </span>
                    <span className="block truncate text-slate-500">
                      {groupLabel(index.group[i])} ·{' '}
                      {shortGminaName(index.gminaNames[index.gmina[i]] ?? index.gmina[i])} ·{' '}
                      {index.critClass[i]}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {query.trim().length < 2 && (
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
                  Obiekty o największym zasięgu
                </p>
                <div className="space-y-1">
                  {suggestions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setSeedId(s.id)}
                      className={`block w-full rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                        seedId === s.id ? 'bg-gov/15 text-gov' : 'text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      <span className="block truncate font-medium">{s.name}</span>
                      <span className="block text-slate-500">
                        {formatNumber(s.nodes)} obiektów · {formatNumber(s.population)} osób
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <Field label="Tryb">
              <select
                className={inputClass}
                value={mode}
                onChange={(e) => setMode(e.target.value as SimulationMode)}
              >
                {SIMULATION_MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              label={`Horyzont: ${formatHours(horizon)}`}
              hint="Skutki liczone tylko do tej godziny od zdarzenia"
            >
              <input
                type="range"
                min={6}
                max={240}
                step={6}
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-gov"
              />
            </Field>

            <label className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700 ring-1 ring-slate-200">
              <input
                type="checkbox"
                checked={assumeBackups}
                onChange={(e) => setAssumeBackups(e.target.checked)}
                className="mt-0.5 accent-gov"
              />
              <span>
                Załóż, że wszystkie agregaty są sprawne.
                <span className="mt-0.5 block text-slate-500">
                  Różnica między tym wynikiem a domyślnym to koszt niesprawnej rezerwy — inny
                  problem i inny budżet niż brak rezerwy w ogóle.
                </span>
              </span>
            </label>
          </div>
        </Panel>

        <div className="space-y-4">
          {!result ? (
            <EmptyState text="Wskaż obiekt po lewej, żeby zobaczyć skutki jego awarii." />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard
                  label="Obiekty, które przestaną działać"
                  value={result.nodesFailed}
                  hint={`w tym ${formatNumber(result.nodesSecondary)} wtórnie, przez zależności`}
                  emphasis
                />
                <KpiCard
                  label="Mieszkańcy bez usługi"
                  value={result.affectedPopulation}
                  hint={`${formatNumber(result.affectedGminas.size)} gmin · woda, prąd, zdrowie`}
                />
                <KpiCard
                  label="Obiekty klasy K1"
                  value={result.k1Failed}
                  hint="najwyższa klasa krytyczności"
                />
                <KpiCard
                  label="Pierwszy skutek wtórny"
                  value={result.firstSecondaryHour}
                  unit=" h"
                  higherIsWorse={false}
                  hint={`fal propagacji: ${result.maxWave}`}
                />
              </div>

              <Panel
                title="Zasięg przestrzenny"
                subtitle="Barwa oznacza numer fali — czerwony to obiekt inicjujący"
                right={
                  <div className="flex gap-2">
                    <Button variant="ghost" onClick={exportCsv}>
                      Pobierz listę CSV
                    </Button>
                    {canWrite(actor.role) && (
                      <Button variant="primary" onClick={() => setSaveOpen(true)}>
                        Zapisz jako scenariusz ćwiczebny
                      </Button>
                    )}
                  </div>
                }
              >
                <CountryMap
                  points={points}
                  colorFor={waveColor}
                  height={420}
                  selectedId={seedId}
                  onSelect={setSeedId}
                  legend={WAVE_COLORS.slice(0, Math.max(result.maxWave + 1, 2)).map((_, i) => ({
                    label: i === 0 ? 'obiekt inicjujący' : `fala ${i}`,
                    value: i,
                  }))}
                />
              </Panel>

              <div className="grid gap-4 xl:grid-cols-2">
                <Panel
                  title={`Pierwsze ${SHOCK_HOURS} godzin`}
                  subtitle="Zanim sztab zdąży się zebrać"
                  tone={shock.length > 1 ? 'alert' : 'default'}
                >
                  {shock.length <= 1 ? (
                    <p className="text-sm text-slate-600">
                      W pierwszych {SHOCK_HOURS} godzinach nie ma skutków wtórnych. Bufory
                      autonomiczne odsuwają propagację poza ten czas — to margines na reakcję.
                    </p>
                  ) : (
                    <div className="max-h-72 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-white text-left text-slate-500">
                          <tr>
                            <th className="py-1.5 font-medium">Godzina</th>
                            <th className="py-1.5 font-medium">Obiekt</th>
                            <th className="py-1.5 font-medium">Gmina</th>
                            <th className="py-1.5 font-medium">Powód</th>
                          </tr>
                        </thead>
                        <tbody>
                          {shock.map((e) => (
                            <tr key={e.node} className="border-t border-slate-100">
                              <td className="py-1.5 tabular-nums text-slate-700">
                                H+{formatNumber(e.failHour, 1)}
                              </td>
                              <td className="py-1.5">
                                <span className="flex items-center gap-1.5">
                                  <span
                                    className="h-2 w-2 shrink-0 rounded-full"
                                    style={{ background: groupColor(index.group[e.node]) }}
                                  />
                                  <span className="truncate text-slate-900">
                                    {shortNodeName(index.name[e.node])}
                                  </span>
                                </span>
                              </td>
                              <td className="py-1.5 truncate text-slate-600">
                                {shortGminaName(
                                  index.gminaNames[index.gmina[e.node]] ?? index.gmina[e.node],
                                )}
                              </td>
                              <td className="py-1.5 text-slate-600">{e.dependency}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Panel>

                <Panel title="Skutki według systemów" subtitle="Ile obiektów w każdej dziedzinie">
                  <BarList rows={groupRows} unit=" ob." />
                  {result.saved.size > 0 && (
                    <p className="mt-3 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-800 ring-1 ring-green-600/20">
                      {formatNumber(result.saved.size)} obiektów nie padnie mimo utraty dostawcy —
                      ich zapas autonomiczny jest dłuższy niż czas przywrócenia zasilania.
                    </p>
                  )}
                </Panel>
              </div>

              {seeGraph ? (
                <Panel
                  title="Drzewo skutków"
                  subtitle="Rozwiń gałąź, żeby zobaczyć, co pociąga za sobą dany obiekt"
                  right={
                    <Button
                      variant="ghost"
                      onClick={() =>
                        setExpanded(
                          expanded.size
                            ? new Set()
                            : new Set(result.events.filter((e) => e.wave === 0).map((e) => e.node)),
                        )
                      }
                    >
                      {expanded.size ? 'Zwiń wszystko' : 'Rozwiń pierwszy poziom'}
                    </Button>
                  }
                >
                  <div className="max-h-96 overflow-y-auto pr-2">{renderBranch(null, 0)}</div>
                </Panel>
              ) : (
                <Panel title="Drzewo skutków">
                  <p className="text-sm text-slate-600">
                    Rola „operator IK" widzi skutki awarii własnych obiektów, ale nie pełny graf
                    zależności między podmiotami. Pełen obraz mają RCB, wojewoda i decydent.
                  </p>
                </Panel>
              )}
            </>
          )}
        </div>
      </div>

      <Modal
        open={saveOpen}
        title="Zapisz scenariusz ćwiczebny"
        onClose={() => setSaveOpen(false)}
      >
        <div className="space-y-3">
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            Zapisujesz wynik, nie decyzję. Scenariusz trafia do rejestru ćwiczeń, żeby dało się do
            niego wrócić i porównać z wariantem po wzmocnieniach.
          </p>
          <Field label="Nazwa scenariusza">
            <input
              className={inputClass}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="np. Utrata GPZ Wschód — ćwiczenie wojewódzkie"
            />
          </Field>
          <Field label="Notatka" hint="Do czego ten scenariusz ma posłużyć">
            <textarea
              className={inputClass}
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </Field>
          {result && (
            <dl className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs sm:grid-cols-4">
              {[
                ['Obiekty', formatNumber(result.nodesFailed)],
                ['Wtórne', formatNumber(result.nodesSecondary)],
                ['Ludność', formatNumber(result.affectedPopulation)],
                ['Horyzont', formatHours(horizon)],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="font-semibold tabular-nums text-slate-900">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          {errors.length > 0 && (
            <ul className="space-y-1 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setSaveOpen(false)}>Anuluj</Button>
            <Button variant="primary" onClick={() => void submit()}>
              Zapisz
            </Button>
          </div>
        </div>
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
