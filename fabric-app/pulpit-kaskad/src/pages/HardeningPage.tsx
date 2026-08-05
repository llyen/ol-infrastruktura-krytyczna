import { useMemo, useState } from 'react';

import {
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
import { simulate } from '@/data/cascade';
import {
  formatHours,
  formatNumber,
  frameTime,
  groupLabel,
  shortGminaName,
  shortNodeName,
} from '@/data/model';
import { useScenario } from '@/hooks/ScenarioContext';
import { HARDENING_ROLES, saveHardeningDecision } from '@/services/workflow';

/**
 * O ile godzin wzmocnienie podnosi autonomię obiektu.
 *
 * Jedna liczba dla całego koszyka jest celowa: demonstracja pokazuje, że
 * różnica bierze się z **wyboru obiektów**, a nie z dobierania parametrów
 * pod z góry założony wynik.
 */
const HARDENING_BONUS_H = 24;

export function HardeningPage() {
  const { index, loading, error, frame, actor, hardening, refresh } = useScenario();
  const [basket, setBasket] = useState<Set<number>>(new Set());
  const [variant, setVariant] = useState('WŁASNY');
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [justification, setJustification] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  /** Zdarzenia inicjujące powódź — węzły fali zerowej wraz z godziną zalania. */
  const seeds = useMemo(() => {
    const map = new Map<number, number>();
    if (!index) return map;
    index.scene.floodFrames.forEach((rows, f) => {
      for (const [node, wave] of rows) {
        if (wave === 0) map.set(node, f * index.scene.meta.frameHours);
      }
    });
    return map;
  }, [index]);

  const baseline = useMemo(() => {
    if (!index || seeds.size === 0) return null;
    return simulate(index, { seeds, horizonHours: 240 });
  }, [index, seeds]);

  /**
   * Wynik po wzmocnieniach liczony jest tym samym silnikiem, co obraz bieżący.
   * Nie ma osobnej tabeli „wariantów po zmianie" — liczba na ekranie bierze
   * się z ponownej propagacji, więc odjęcie obiektu z koszyka naprawdę
   * pogarsza wynik.
   */
  const improved = useMemo(() => {
    if (!index || seeds.size === 0 || basket.size === 0) return null;
    const bonus = new Map<number, number>();
    for (const n of basket) bonus.set(n, HARDENING_BONUS_H);
    return simulate(index, { seeds, horizonHours: 240, autonomyBonus: bonus });
  }, [index, seeds, basket]);

  const candidates = useMemo(() => {
    if (!index) return [];
    return index.scene.marginal
      .filter(([node]) => !actor.voivodeshipCode || index.voiv[node] === actor.voivodeshipCode)
      .slice(0, 60);
  }, [index, actor.voivodeshipCode]);

  const toggle = (node: number) => {
    setBasket((prev) => {
      const next = new Set(prev);
      if (next.has(node)) next.delete(node);
      else next.add(node);
      return next;
    });
    setVariant('WŁASNY');
  };

  if (loading) return <EmptyState text="Wczytywanie planu wzmocnień…" />;
  if (error) return <EmptyState text={error} />;
  if (!index) return null;

  const sceneTime = frameTime(index.scene.meta, frame).toISOString();
  const canApprove = HARDENING_ROLES.includes(actor.role);
  const nodesSaved = baseline && improved ? baseline.nodesFailed - improved.nodesFailed : 0;
  const populationSaved =
    baseline && improved ? baseline.affectedPopulation - improved.affectedPopulation : 0;

  /** Wczytanie gotowego wariantu: bierzemy tylu najskuteczniejszych kandydatów, ile obejmuje wariant. */
  const loadVariant = (name: string, hardenedNodes: number) => {
    setVariant(name);
    setBasket(new Set(candidates.slice(0, Math.min(hardenedNodes, candidates.length)).map((r) => r[0])));
  };

  const submit = async () => {
    const draft = {
      scene_time: sceneTime,
      variant,
      node_ids: [...basket].map((n) => index.id[n]).join(','),
      node_count: basket.size,
      nodes_saved: nodesSaved,
      population_saved: populationSaved,
      decision: 'zatwierdzony',
      justification,
      supersedes: hardening[0]?.decision_id ?? '',
    };
    try {
      await saveHardeningDecision(draft, actor);
      await refresh();
      setDecisionOpen(false);
      setJustification('');
      setErrors([]);
      setToast('Plan wzmocnień zatwierdzony i zapisany w rejestrze decyzji.');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const exportBasket = () => {
    const head = 'node_id;nazwa;system;gmina;autonomia_h;obiekty_uratowane;ludnosc_uratowana\n';
    const byNode = new Map(index.scene.marginal.map((r) => [r[0], r]));
    const body = [...basket]
      .map((n) => {
        const m = byNode.get(n);
        return [
          index.id[n],
          index.name[n],
          index.systemCode[n],
          index.gminaNames[index.gmina[n]] ?? index.gmina[n],
          m?.[1] ?? index.autonomyH[n],
          m?.[2] ?? 0,
          m?.[3] ?? 0,
        ].join(';');
      })
      .join('\n');
    downloadCsv('plan-wzmocnien.csv', head + body);
  };

  return (
    <div className="space-y-4">
      <Panel
        title="Warianty wzmocnień"
        subtitle="Policzone poza aplikacją na tym samym scenariuszu powodziowym — punkt odniesienia dla własnego koszyka"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1.5 font-medium">Wariant</th>
                <th className="py-1.5 font-medium">Zakres</th>
                <th className="py-1.5 font-medium">Wzmocnione</th>
                <th className="py-1.5 font-medium">Obiekty poza pracą</th>
                <th className="py-1.5 font-medium">Skutki wtórne</th>
                <th className="py-1.5 font-medium">Ludność</th>
                <th className="py-1.5 font-medium">Redukcja wtórnych</th>
                <th className="py-1.5" />
              </tr>
            </thead>
            <tbody>
              {index.scene.variants.map((v) => (
                <tr key={v.variant} className="border-t border-slate-100">
                  <td className="py-2 font-semibold text-slate-900">{v.variant}</td>
                  <td className="py-2 max-w-[280px] text-slate-600">{v.description}</td>
                  <td className="py-2 tabular-nums text-slate-600">
                    {formatNumber(v.hardenedNodes)}
                  </td>
                  <td className="py-2 tabular-nums text-slate-900">{formatNumber(v.nodesFailed)}</td>
                  <td className="py-2 tabular-nums text-slate-600">
                    {formatNumber(v.nodesSecondary)}
                  </td>
                  <td className="py-2 tabular-nums text-slate-600">
                    {formatNumber(v.population)}
                  </td>
                  <td
                    className="py-2 font-semibold tabular-nums"
                    style={{ color: v.secondaryReductionPct > 0 ? '#15803d' : '#64748b' }}
                  >
                    {v.secondaryReductionPct > 0 ? '−' : ''}
                    {formatNumber(Math.abs(v.secondaryReductionPct), 1)}%
                  </td>
                  <td className="py-2 text-right">
                    {v.hardenedNodes > 0 && (
                      <Button
                        variant="ghost"
                        onClick={() => loadVariant(v.variant, v.hardenedNodes)}
                      >
                        Wczytaj do koszyka
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Panel
          title="Wartość krańcowa wzmocnienia"
          subtitle={`Ile obiektów i ludzi ratuje podniesienie autonomii o ${HARDENING_BONUS_H} h na tym jednym obiekcie`}
        >
          <div className="max-h-[480px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white text-left text-slate-500">
                <tr>
                  <th className="py-1.5 font-medium" />
                  <th className="py-1.5 font-medium">Obiekt</th>
                  <th className="py-1.5 font-medium">System</th>
                  <th className="py-1.5 font-medium">Autonomia</th>
                  <th className="py-1.5 font-medium">Uratowane obiekty</th>
                  <th className="py-1.5 font-medium">Uratowani ludzie</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map(([node, autonomy, saved, pop]) => (
                  <tr
                    key={node}
                    className={`border-t border-slate-100 ${
                      basket.has(node) ? 'bg-gov/10' : ''
                    }`}
                  >
                    <td className="py-1.5">
                      <input
                        type="checkbox"
                        checked={basket.has(node)}
                        onChange={() => toggle(node)}
                        className="accent-gov"
                        aria-label={`Dodaj ${index.name[node]} do koszyka`}
                      />
                    </td>
                    <td className="py-1.5">
                      <span className="block truncate text-slate-900">
                        {shortNodeName(index.name[node])}
                      </span>
                      <span className="block truncate text-slate-500">
                        {shortGminaName(index.gminaNames[index.gmina[node]] ?? index.gmina[node])}
                      </span>
                    </td>
                    <td className="py-1.5 text-slate-600">{groupLabel(index.group[node])}</td>
                    <td className="py-1.5 tabular-nums text-slate-600">{formatHours(autonomy)}</td>
                    <td className="py-1.5 font-semibold tabular-nums text-slate-900">
                      {formatNumber(saved)}
                    </td>
                    <td className="py-1.5 tabular-nums text-slate-600">{formatNumber(pop)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <KpiCard
              label="Obiekty w koszyku"
              value={basket.size}
              higherIsWorse={false}
              hint={`wariant: ${variant}`}
            />
            <KpiCard
              label="Obiekty uratowane"
              value={nodesSaved}
              higherIsWorse={false}
              hint="różnica względem przebiegu bez wzmocnień"
              emphasis
            />
          </div>

          <Panel
            title="Skutek koszyka"
            subtitle="Liczby biorą się z ponownej propagacji, nie z tabeli"
            right={
              basket.size > 0 && (
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={exportBasket}>
                    CSV
                  </Button>
                  <Button variant="ghost" onClick={() => setBasket(new Set())}>
                    Wyczyść
                  </Button>
                </div>
              )
            }
          >
            {!baseline ? (
              <EmptyState text="Brak danych scenariusza powodziowego." />
            ) : basket.size === 0 ? (
              <div className="space-y-2 text-sm text-slate-600">
                <p>
                  Koszyk jest pusty. Bez wzmocnień powódź wyłącza{' '}
                  <strong className="text-slate-900">{formatNumber(baseline.nodesFailed)}</strong>{' '}
                  obiektów, z czego {formatNumber(baseline.nodesSecondary)} przez zależności,
                  i pozbawia usług {formatNumber(baseline.affectedPopulation)} mieszkańców.
                </p>
                <p className="text-xs text-slate-500">
                  Zaznacz obiekty po lewej albo wczytaj gotowy wariant, żeby zobaczyć różnicę.
                </p>
              </div>
            ) : (
              <dl className="space-y-2 text-sm">
                {[
                  [
                    'Obiekty poza pracą',
                    baseline.nodesFailed,
                    improved?.nodesFailed ?? baseline.nodesFailed,
                  ],
                  [
                    'Skutki wtórne',
                    baseline.nodesSecondary,
                    improved?.nodesSecondary ?? baseline.nodesSecondary,
                  ],
                  [
                    'Mieszkańcy bez usługi',
                    baseline.affectedPopulation,
                    improved?.affectedPopulation ?? baseline.affectedPopulation,
                  ],
                  ['Obiekty K1', baseline.k1Failed, improved?.k1Failed ?? baseline.k1Failed],
                ].map(([label, before, after]) => {
                  const b = before as number;
                  const a = after as number;
                  const delta = b - a;
                  return (
                    <div
                      key={label as string}
                      className="flex items-baseline justify-between gap-3 border-b border-slate-100 pb-1.5"
                    >
                      <dt className="text-xs text-slate-600">{label}</dt>
                      <dd className="flex items-baseline gap-2 tabular-nums">
                        <span className="text-xs text-slate-400 line-through">
                          {formatNumber(b)}
                        </span>
                        <span className="font-semibold text-slate-900">{formatNumber(a)}</span>
                        <span
                          className="w-20 text-right text-xs font-semibold"
                          style={{ color: delta > 0 ? '#15803d' : '#64748b' }}
                        >
                          {delta > 0 ? `−${formatNumber(delta)}` : '—'}
                        </span>
                      </dd>
                    </div>
                  );
                })}
              </dl>
            )}

            {canApprove ? (
              <Button
                variant="primary"
                className="mt-3 w-full"
                onClick={() => setDecisionOpen(true)}
                disabled={basket.size === 0}
              >
                Zatwierdź plan wzmocnień
              </Button>
            ) : (
              <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                Plan wzmocnień zatwierdza decydent. W innych rolach koszyk służy do
                przygotowania wniosku.
              </p>
            )}
          </Panel>

          <Panel title="Rejestr decyzji">
            {hardening.length === 0 ? (
              <EmptyState text="Nie ma jeszcze zatwierdzonych planów." />
            ) : (
              <ul className="max-h-60 space-y-2 overflow-y-auto">
                {hardening.map((h) => (
                  <li key={h.id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs">
                    <span className="font-medium text-slate-900">
                      {h.decision_id} · wariant {h.variant}
                    </span>
                    <span className="mt-0.5 block text-slate-600">
                      {formatNumber(h.node_count)} obiektów · uratowane:{' '}
                      {formatNumber(h.nodes_saved)} obiektów,{' '}
                      {formatNumber(h.population_saved)} osób
                    </span>
                    <span className="mt-0.5 block text-slate-500">
                      {h.author_name} ({h.author_role})
                      {h.supersedes && ` · zastępuje ${h.supersedes}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <Modal open={decisionOpen} title="Zatwierdzenie planu wzmocnień" onClose={() => setDecisionOpen(false)}>
        <div className="space-y-3">
          <dl className="grid grid-cols-3 gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs">
            <div>
              <dt className="text-slate-500">Obiekty</dt>
              <dd className="font-semibold text-slate-900">{formatNumber(basket.size)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Uratowane obiekty</dt>
              <dd className="font-semibold text-slate-900">{formatNumber(nodesSaved)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Uratowani ludzie</dt>
              <dd className="font-semibold text-slate-900">{formatNumber(populationSaved)}</dd>
            </div>
          </dl>
          <Field label="Uzasadnienie" hint="Minimum 30 znaków — decyzja trafia do rejestru">
            <textarea
              className={inputClass}
              rows={4}
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder="Dlaczego akurat te obiekty i dlaczego teraz"
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
            <Button onClick={() => setDecisionOpen(false)}>Anuluj</Button>
            <Button variant="primary" onClick={() => void submit()}>
              Zatwierdź
            </Button>
          </div>
        </div>
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
