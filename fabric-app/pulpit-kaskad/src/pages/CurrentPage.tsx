import { useMemo, useState } from 'react';

import { CountryMap, type MapPoint } from '@/components/CountryMap';
import {
  Button,
  EmptyState,
  Field,
  KpiCard,
  Modal,
  Panel,
  TimelineBars,
  Toast,
  downloadCsv,
  inputClass,
} from '@/components/ui';
import {
  formatHours,
  formatNumber,
  frameTime,
  groupColor,
  groupLabel,
  severityColor,
  shortGminaName,
  shortNodeName,
} from '@/data/model';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  FUEL_ROLES,
  FUEL_URGENT_H,
  canActOn,
  fuelPriority,
  saveFuelRequest,
  suggestedLitres,
} from '@/services/workflow';

/** Ile godzin do przodu pokazuje prognoza propagacji. */
const FORECAST_H = 12;

/** Do której godziny zapasu ma wystarczyć dowożone paliwo. */
const FUEL_TARGET_H = 48;

interface FailedNode {
  node: number;
  wave: number;
  failHour: number;
}

export function CurrentPage() {
  const { index, loading, error, frame, actor, fuelRequests, refresh } = useScenario();
  const [selected, setSelected] = useState<string | null>(null);
  const [fuelNode, setFuelNode] = useState<number | null>(null);
  const [litres, setLitres] = useState(0);
  const [justification, setJustification] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  /** Kumulacja klatek: w chwili N widać wszystko, co padło do godziny N. */
  const failed = useMemo<FailedNode[]>(() => {
    if (!index) return [];
    const out: FailedNode[] = [];
    const frames = index.scene.floodFrames;
    for (let f = 0; f <= frame && f < frames.length; f += 1) {
      for (const [node, wave] of frames[f]) {
        out.push({ node, wave, failHour: f * index.scene.meta.frameHours });
      }
    }
    return out;
  }, [index, frame]);

  const inScope = useMemo(() => {
    if (!index) return failed;
    if (!actor.voivodeshipCode) return failed;
    return failed.filter((f) => index.voiv[f.node] === actor.voivodeshipCode);
  }, [failed, index, actor.voivodeshipCode]);

  const stats = useMemo(() => {
    if (!index) return { k1: 0, population: 0, gminas: 0 };
    const gminas = new Set<string>();
    let k1 = 0;
    for (const f of inScope) {
      if (index.critClass[f.node] === 'K1') k1 += 1;
      const g = index.group[f.node];
      if (g === 'energy' || g === 'water' || g === 'health') gminas.add(index.gmina[f.node]);
    }
    let population = 0;
    for (const g of gminas) population += index.gminaPopulation[g] ?? 0;
    return { k1, population, gminas: gminas.size };
  }, [inScope, index]);

  /** Przebieg narastania awarii — pełna oś czasu, nie tylko chwila bieżąca. */
  const timeline = useMemo(() => {
    if (!index) return { values: [], labels: [] as string[] };
    let running = 0;
    const values: number[] = [];
    const labels: string[] = [];
    index.scene.floodFrames.forEach((rows, i) => {
      running += rows.length;
      values.push(running);
      labels.push(`H+${i}`);
    });
    return { values, labels };
  }, [index]);

  const points: MapPoint[] = useMemo(() => {
    if (!index) return [];
    return inScope.map((f) => ({
      id: index.id[f.node],
      lat: index.lat[f.node],
      lon: index.lon[f.node],
      value: index.critClass[f.node] === 'K1' ? 90 : index.critScore[f.node],
      label: shortNodeName(index.name[f.node]),
      detail: `${groupLabel(index.group[f.node])} · H+${formatNumber(f.failHour)} · ${
        index.critClass[f.node]
      }`,
      alarm: index.critClass[f.node] === 'K1',
    }));
  }, [inScope, index]);

  const k1List = useMemo(() => {
    if (!index) return [];
    return inScope
      .filter((f) => index.critClass[f.node] === 'K1')
      .sort((a, b) => a.failHour - b.failHour)
      .slice(0, 60);
  }, [inScope, index]);

  /**
   * Kolejka paliwowa.
   *
   * Zapas liczony jest od godziny, w której obiekt stracił zasilanie
   * podstawowe, a nie od początku scenariusza — inaczej lista pokazywałaby
   * jako pilne obiekty, które padły przed chwilą i mają pełny zbiornik.
   */
  const fuelQueue = useMemo(() => {
    if (!index) return [];
    const now = frame * index.scene.meta.frameHours;
    const requested = new Set(fuelRequests.map((r) => r.node_id));
    return inScope
      .filter((f) => {
        const b = index.backupType[f.node];
        return (b === 'genset' || b === 'onsite_fuel') && index.fuelH[f.node] > 0;
      })
      .map((f) => ({
        ...f,
        remaining: index.fuelH[f.node] - (now - f.failHour),
        pending: requested.has(index.id[f.node]),
      }))
      .filter((f) => f.remaining < 24)
      .sort((a, b) => a.remaining - b.remaining)
      .slice(0, 40);
  }, [inScope, index, frame, fuelRequests]);

  const forecast = useMemo(() => {
    if (!index) return [];
    const frames = index.scene.floodFrames;
    const out: FailedNode[] = [];
    for (let f = frame + 1; f <= frame + FORECAST_H && f < frames.length; f += 1) {
      for (const [node, wave] of frames[f]) {
        if (actor.voivodeshipCode && index.voiv[node] !== actor.voivodeshipCode) continue;
        out.push({ node, wave, failHour: f * index.scene.meta.frameHours });
      }
    }
    return out.slice(0, 60);
  }, [index, frame, actor.voivodeshipCode]);

  if (loading) return <EmptyState text="Wczytywanie obrazu bieżącego…" />;
  if (error) return <EmptyState text={error} />;
  if (!index) return null;

  const sceneTime = frameTime(index.scene.meta, frame).toISOString();
  const canRequestFuel = FUEL_ROLES.includes(actor.role);

  const openFuel = (node: number, remaining: number) => {
    setFuelNode(node);
    setLitres(suggestedLitres(remaining, FUEL_TARGET_H));
    setJustification('');
    setErrors([]);
  };

  const submitFuel = async () => {
    if (fuelNode === null) return;
    const now = frame * index.scene.meta.frameHours;
    const failAt = inScope.find((f) => f.node === fuelNode)?.failHour ?? now;
    const remaining = index.fuelH[fuelNode] - (now - failAt);
    const draft = {
      scene_time: sceneTime,
      node_id: index.id[fuelNode],
      node_name: index.name[fuelNode],
      voivodeship_code: index.voiv[fuelNode],
      gmina_code: index.gmina[fuelNode],
      operator_name: index.operator[fuelNode],
      hours_remaining: Math.round(remaining * 10) / 10,
      litres_requested: litres,
      priority: fuelPriority(remaining, index.critClass[fuelNode]),
      justification,
      status: 'zgłoszone',
    };
    try {
      await saveFuelRequest(draft, actor);
      await refresh();
      setFuelNode(null);
      setToast('Zapotrzebowanie na paliwo zgłoszone do wojewódzkiego sztabu.');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const exportQueue = () => {
    const head = 'node_id;nazwa;operator;gmina;klasa;godziny_zapasu;priorytet\n';
    const body = fuelQueue
      .map((f) =>
        [
          index.id[f.node],
          index.name[f.node],
          index.operator[f.node],
          index.gminaNames[index.gmina[f.node]] ?? index.gmina[f.node],
          index.critClass[f.node],
          Math.round(f.remaining * 10) / 10,
          fuelPriority(f.remaining, index.critClass[f.node]),
        ].join(';'),
      )
      .join('\n');
    downloadCsv('kolejka-paliwowa.csv', head + body);
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Obiekty niedziałające"
          value={inScope.length}
          hint={`z ${formatNumber(index.count)} w rejestrze`}
          spark={timeline.values.slice(0, frame + 1)}
          emphasis
        />
        <KpiCard
          label="Obiekty klasy K1"
          value={stats.k1}
          hint="wymagają decyzji sztabu, nie kolejki"
        />
        <KpiCard
          label="Mieszkańcy bez usługi"
          value={stats.population}
          hint={`${formatNumber(stats.gminas)} gmin`}
        />
        <KpiCard
          label="Obiekty na rezerwie paliwowej"
          value={fuelQueue.length}
          hint={`w tym ${formatNumber(
            fuelQueue.filter((f) => f.remaining < FUEL_URGENT_H).length,
          )} poniżej ${FUEL_URGENT_H} h zapasu`}
        />
      </div>

      <Panel
        title="Przebieg awarii"
        subtitle="Narastanie liczby niedziałających obiektów w kolejnych godzinach powodzi"
      >
        <TimelineBars
          values={timeline.values}
          labels={timeline.labels}
          activeIndex={frame}
          height={64}
          colorFor={(v) => severityColor((v / Math.max(...timeline.values, 1)) * 100)}
        />
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Panel
          title="Obraz przestrzenny"
          subtitle="Obiekty, które przestały działać do bieżącej godziny"
        >
          <CountryMap
            points={points}
            colorFor={severityColor}
            height={460}
            selectedId={selected}
            onSelect={setSelected}
            legend={[
              { label: 'niska krytyczność', value: 10 },
              { label: 'podwyższona', value: 40 },
              { label: 'wysoka', value: 60 },
              { label: 'K1', value: 90 },
            ]}
          />
        </Panel>

        <Panel
          title="Obiekty K1 poza pracą"
          subtitle="Najwyższa klasa krytyczności — kolejność według godziny awarii"
          tone={k1List.length > 0 ? 'alert' : 'default'}
        >
          {k1List.length === 0 ? (
            <EmptyState text="Żaden obiekt klasy K1 nie jest jeszcze wyłączony." />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-white text-left text-slate-500">
                  <tr>
                    <th className="py-1.5 font-medium">H+</th>
                    <th className="py-1.5 font-medium">Obiekt</th>
                    <th className="py-1.5 font-medium">Gmina</th>
                    <th className="py-1.5 font-medium">Rezerwa</th>
                  </tr>
                </thead>
                <tbody>
                  {k1List.map((f) => (
                    <tr key={f.node} className="border-t border-slate-100">
                      <td className="py-1.5 tabular-nums text-slate-700">
                        {formatNumber(f.failHour)}
                      </td>
                      <td className="py-1.5">
                        <span className="flex items-center gap-1.5">
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ background: groupColor(index.group[f.node]) }}
                          />
                          <span className="truncate text-slate-900">
                            {shortNodeName(index.name[f.node])}
                          </span>
                        </span>
                      </td>
                      <td className="py-1.5 truncate text-slate-600">
                        {shortGminaName(index.gminaNames[index.gmina[f.node]] ?? index.gmina[f.node])}
                      </td>
                      <td className="py-1.5 text-slate-600">
                        {index.backupType[f.node] === 'none'
                          ? '— brak'
                          : formatHours(index.autonomyH[f.node])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Panel
          title="Kolejka paliwowa"
          subtitle={`Zapas liczony od chwili utraty zasilania · cel dowozu: ${FUEL_TARGET_H} h autonomii`}
          right={
            <Button variant="ghost" onClick={exportQueue}>
              Pobierz CSV
            </Button>
          }
          tone={fuelQueue.some((f) => f.remaining < FUEL_URGENT_H) ? 'alert' : 'default'}
        >
          {fuelQueue.length === 0 ? (
            <EmptyState text="Żaden obiekt na rezerwie paliwowej nie schodzi poniżej doby zapasu." />
          ) : (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-white text-left text-slate-500">
                  <tr>
                    <th className="py-1.5 font-medium">Zapas</th>
                    <th className="py-1.5 font-medium">Obiekt</th>
                    <th className="py-1.5 font-medium">Operator</th>
                    <th className="py-1.5 font-medium">Priorytet</th>
                    <th className="py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {fuelQueue.map((f) => {
                    const priority = fuelPriority(f.remaining, index.critClass[f.node]);
                    const allowed =
                      canRequestFuel &&
                      canActOn(actor, {
                        voiv: index.voiv[f.node],
                        operator: index.operator[f.node],
                      });
                    return (
                      <tr key={f.node} className="border-t border-slate-100">
                        <td
                          className="py-1.5 font-semibold tabular-nums"
                          style={{ color: f.remaining < FUEL_URGENT_H ? '#d5233f' : '#334155' }}
                        >
                          {f.remaining <= 0 ? 'wyczerpany' : formatHours(f.remaining)}
                        </td>
                        <td className="py-1.5 truncate text-slate-900">
                          {shortNodeName(index.name[f.node])}
                        </td>
                        <td className="py-1.5 truncate text-slate-600">{index.operator[f.node]}</td>
                        <td className="py-1.5">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                              priority === 'pilny'
                                ? 'bg-red-50 text-red-700'
                                : priority === 'podwyższony'
                                  ? 'bg-amber-50 text-amber-700'
                                  : 'bg-slate-100 text-slate-600'
                            }`}
                          >
                            {priority}
                          </span>
                        </td>
                        <td className="py-1.5 text-right">
                          {f.pending ? (
                            <span className="text-[10px] text-slate-500">zgłoszone</span>
                          ) : (
                            allowed && (
                              <Button
                                variant="ghost"
                                onClick={() => openFuel(f.node, f.remaining)}
                              >
                                Zgłoś
                              </Button>
                            )
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          title={`Prognoza na ${FORECAST_H} godzin`}
          subtitle="Obiekty, które padną, jeśli nic się nie zmieni"
        >
          {forecast.length === 0 ? (
            <EmptyState text="W najbliższych godzinach propagacja się zatrzymuje." />
          ) : (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-white text-left text-slate-500">
                  <tr>
                    <th className="py-1.5 font-medium">H+</th>
                    <th className="py-1.5 font-medium">Obiekt</th>
                    <th className="py-1.5 font-medium">System</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.map((f) => (
                    <tr key={f.node} className="border-t border-slate-100">
                      <td className="py-1.5 tabular-nums text-slate-700">
                        {formatNumber(f.failHour)}
                      </td>
                      <td className="py-1.5 truncate text-slate-900">
                        {shortNodeName(index.name[f.node])}
                        {index.critClass[f.node] === 'K1' && (
                          <span className="ml-1 rounded bg-red-50 px-1 py-0.5 text-[10px] font-semibold text-red-700">
                            K1
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 text-slate-600">{groupLabel(index.group[f.node])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <Modal
        open={fuelNode !== null}
        title="Zapotrzebowanie na paliwo"
        onClose={() => setFuelNode(null)}
      >
        {fuelNode !== null && (
          <div className="space-y-3">
            <dl className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs">
              <div>
                <dt className="text-slate-500">Obiekt</dt>
                <dd className="font-medium text-slate-900">
                  {shortNodeName(index.name[fuelNode])}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Operator</dt>
                <dd className="font-medium text-slate-900">{index.operator[fuelNode]}</dd>
              </div>
            </dl>
            <Field
              label="Ilość paliwa (litry)"
              hint={`Podpowiedź wynika z celu ${FUEL_TARGET_H} h autonomii przy zużyciu agregatu średniej mocy.`}
            >
              <input
                className={inputClass}
                type="number"
                min={0}
                step={50}
                value={litres}
                onChange={(e) => setLitres(Number(e.target.value))}
              />
            </Field>
            <Field label="Uzasadnienie" hint="Minimum 30 znaków — trafia do rejestru decyzji">
              <textarea
                className={inputClass}
                rows={3}
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
              />
            </Field>
            {errors.length > 0 && (
              <ul className="space-y-1 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            <div className="flex justify-end gap-2">
              <Button onClick={() => setFuelNode(null)}>Anuluj</Button>
              <Button variant="primary" onClick={() => void submitFuel()}>
                Zgłoś zapotrzebowanie
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
