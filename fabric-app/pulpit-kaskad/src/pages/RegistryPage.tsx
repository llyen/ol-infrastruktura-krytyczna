import { useMemo, useState } from 'react';

import {
  Badge,
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
  formatHours,
  formatNumber,
  frameTime,
  groupLabel,
  shortGminaName,
  shortNodeName,
} from '@/data/model';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  COOPERATION_ACTIONS,
  COOPERATION_ROLES,
  cooperationGaps,
  saveCooperationAction,
} from '@/services/workflow';

const dateFormat = new Intl.DateTimeFormat('pl-PL', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

function inThirtyDays(): string {
  return new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
}

export function RegistryPage() {
  const { index, loading, error, frame, actor, cooperation, refresh } = useScenario();
  const [query, setQuery] = useState('');
  const [nodeId, setNodeId] = useState('');
  const [actionOpen, setActionOpen] = useState(false);
  const [actionKind, setActionKind] = useState<string>(COOPERATION_ACTIONS[0]);
  const [dueDate, setDueDate] = useState(inThirtyDays());
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  const scopeFilter = useMemo(() => {
    if (!index) return () => true;
    return (i: number) =>
      (!actor.voivodeshipCode || index.voiv[i] === actor.voivodeshipCode) &&
      (actor.role !== 'operator IK' ||
        !actor.operatorName ||
        index.operator[i] === actor.operatorName);
  }, [index, actor.voivodeshipCode, actor.role, actor.operatorName]);

  const matches = useMemo(() => {
    if (!index) return [];
    const q = query.trim().toLowerCase();
    const out: number[] = [];
    for (let i = 0; i < index.count && out.length < 60; i += 1) {
      if (!scopeFilter(i)) continue;
      if (q.length >= 2) {
        const hay = `${index.id[i]} ${index.name[i]} ${index.operator[i]}`.toLowerCase();
        if (!hay.includes(q)) continue;
      } else if (index.critClass[i] !== 'K1') continue;
      out.push(i);
    }
    return out;
  }, [index, query, scopeFilter]);

  const node = useMemo(() => {
    if (!index || !nodeId) return null;
    const i = index.byId.get(nodeId);
    return i === undefined ? null : i;
  }, [index, nodeId]);

  const gaps = useMemo(() => {
    if (!index || node === null) return [];
    return cooperationGaps({
      planStatus: index.planStatus[node],
      hasContact: index.hasContact[node],
      hasAgreement: index.hasAgreement[node],
      onRegister: index.onRegister[node],
      lastContactTest: index.lastContactTest[node],
    });
  }, [index, node]);

  /** Ile obiektów w zakresie użytkownika ma braki w danym wymiarze współpracy. */
  const registerStats = useMemo(() => {
    if (!index) return { total: 0, offRegister: 0, noPlan: 0, noContact: 0 };
    let total = 0;
    let offRegister = 0;
    let noPlan = 0;
    let noContact = 0;
    for (let i = 0; i < index.count; i += 1) {
      if (!scopeFilter(i)) continue;
      total += 1;
      if (!index.onRegister[i]) offRegister += 1;
      if (index.planStatus[i] !== 'zatwierdzony') noPlan += 1;
      if (!index.hasContact[i]) noContact += 1;
    }
    return { total, offRegister, noPlan, noContact };
  }, [index, scopeFilter]);

  const operators = useMemo(() => index?.scene.operators.slice(0, 20) ?? [], [index]);

  if (loading) return <EmptyState text="Wczytywanie rejestru…" />;
  if (error) return <EmptyState text={error} />;
  if (!index) return null;

  const sceneTime = frameTime(index.scene.meta, frame).toISOString();
  const canAct = COOPERATION_ROLES.includes(actor.role);

  const submit = async () => {
    if (node === null) return;
    const draft = {
      scene_time: sceneTime,
      node_id: index.id[node],
      node_name: index.name[node],
      operator_name: index.operator[node],
      voivodeship_code: index.voiv[node],
      action_kind: actionKind,
      gap_reason: gaps.join('; '),
      due_date: dueDate,
      note,
    };
    try {
      await saveCooperationAction(draft, actor);
      await refresh();
      setActionOpen(false);
      setNote('');
      setErrors([]);
      setToast('Działanie zapisane. Trafia na listę zadań współpracy SPO-10.');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const exportOperators = () => {
    const head = 'operator;obiekty;bez_planu;bez_kontaktu;bez_umowy;ludnosc;responsywnosc\n';
    const body = (index.scene.operators ?? [])
      .map((o) =>
        [o.name, o.nodes, o.noPlan, o.noContact, o.noAgreement, o.pop, o.responsiveness].join(';'),
      )
      .join('\n');
    downloadCsv('luki-wspolpracy-spo10.csv', head + body);
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Obiekty w zakresie"
          value={registerStats.total}
          higherIsWorse={false}
          hint="widoczne dla Twojej roli i województwa"
        />
        <KpiCard
          label="Poza rejestrem IK"
          value={registerStats.offRegister}
          hint="obiekty istotne, ale bez formalnego wpisu"
          emphasis
        />
        <KpiCard
          label="Bez zatwierdzonego planu ochrony"
          value={registerStats.noPlan}
          hint="plan w opracowaniu, nieaktualny albo brak"
        />
        <KpiCard
          label="Bez punktu kontaktowego"
          value={registerStats.noContact}
          hint="w kryzysie nie ma do kogo zadzwonić"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[340px_1fr]">
        <Panel title="Znajdź obiekt" subtitle="Bez wyszukiwania lista pokazuje obiekty klasy K1">
          <div className="space-y-3">
            <Field label="Szukaj">
              <input
                className={inputClass}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="nazwa, identyfikator lub operator"
              />
            </Field>
            <div className="max-h-[460px] overflow-y-auto rounded-lg ring-1 ring-slate-200">
              {matches.length === 0 ? (
                <p className="px-3 py-4 text-xs text-slate-500">Brak dopasowań.</p>
              ) : (
                matches.map((i) => (
                  <button
                    key={index.id[i]}
                    type="button"
                    onClick={() => setNodeId(index.id[i])}
                    className={`block w-full px-3 py-2 text-left text-xs transition-colors ${
                      nodeId === index.id[i]
                        ? 'bg-gov/15 text-gov'
                        : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    <span className="block truncate font-medium">
                      {shortNodeName(index.name[i])}
                    </span>
                    <span className="block truncate text-slate-500">
                      {index.critClass[i]} · {index.operator[i]}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </Panel>

        <div className="space-y-4">
          {node === null ? (
            <EmptyState text="Wybierz obiekt, żeby zobaczyć jego kartę i stan współpracy." />
          ) : (
            <>
              <Panel
                title={shortNodeName(index.name[node])}
                subtitle={`${index.id[node]} · ${groupLabel(index.group[node])} · ${
                  index.systemByCode.get(index.systemCode[node])?.name ?? index.systemCode[node]
                }`}
                right={
                  canAct && (
                    <Button variant="primary" onClick={() => setActionOpen(true)}>
                      Zainicjuj działanie
                    </Button>
                  )
                }
                tone={gaps.length >= 3 ? 'alert' : 'default'}
              >
                <dl className="grid gap-3 text-xs sm:grid-cols-3 lg:grid-cols-4">
                  {[
                    ['Klasa krytyczności', index.critClass[node]],
                    ['Operator', index.operator[node]],
                    [
                      'Gmina',
                      shortGminaName(index.gminaNames[index.gmina[node]] ?? index.gmina[node]),
                    ],
                    [
                      'Województwo',
                      index.voivName.get(index.voiv[node]) ?? index.voiv[node],
                    ],
                    ['Obsługiwana ludność', formatNumber(index.population[node])],
                    ['Zasilanie rezerwowe', index.backupType[node]],
                    ['Autonomia', formatHours(index.autonomyH[node])],
                    ['Zapas paliwa', formatHours(index.fuelH[node])],
                    ['Czas przywrócenia', formatHours(index.restoreH[node])],
                    ['Plan ochrony', index.planStatus[node]],
                    [
                      'Ostatni test kontaktu',
                      index.lastContactTest[node]
                        ? dateFormat.format(new Date(index.lastContactTest[node]))
                        : '—',
                    ],
                    [
                      'Ostatnie ćwiczenie',
                      index.lastExercise[node]
                        ? dateFormat.format(new Date(index.lastExercise[node]))
                        : '—',
                    ],
                  ].map(([k, v]) => (
                    <div key={k as string}>
                      <dt className="text-slate-500">{k}</dt>
                      <dd className="font-medium text-slate-900">{v}</dd>
                    </div>
                  ))}
                </dl>

                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge
                    className={
                      index.onRegister[node]
                        ? 'bg-green-50 text-green-800 ring-green-600/20'
                        : 'bg-red-50 text-red-700 ring-red-600/20'
                    }
                  >
                    {index.onRegister[node] ? 'w rejestrze IK' : 'poza rejestrem IK'}
                  </Badge>
                  <Badge
                    className={
                      index.spo10[node]
                        ? 'bg-green-50 text-green-800 ring-green-600/20'
                        : 'bg-amber-50 text-amber-700 ring-amber-600/20'
                    }
                  >
                    {index.spo10[node] ? 'porozumienie SPO-10' : 'brak porozumienia SPO-10'}
                  </Badge>
                  {index.inFloodZone[node] === 1 && (
                    <Badge className="bg-blue-50 text-blue-800 ring-blue-600/20">
                      w strefie zalewowej
                    </Badge>
                  )}
                  <Badge className="bg-slate-100 text-slate-700 ring-slate-300">
                    responsywność {formatNumber(index.responsiveness[node], 1)}
                  </Badge>
                </div>
              </Panel>

              <div className="grid gap-4 xl:grid-cols-2">
                <Panel
                  title="Luki we współpracy"
                  subtitle="Braki wypisane słowami — każdy z nich to konkretne zadanie"
                  tone={gaps.length > 0 ? 'alert' : 'default'}
                >
                  {gaps.length === 0 ? (
                    <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
                      Współpraca z tym operatorem jest kompletna: obiekt w rejestrze, plan
                      zatwierdzony, kontakt przetestowany, umowa o wymianie danych zawarta.
                    </p>
                  ) : (
                    <ul className="space-y-1.5">
                      {gaps.map((g) => (
                        <li
                          key={g}
                          className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-800"
                        >
                          <span aria-hidden>•</span>
                          <span>{g}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>

                <Panel title="Działania zapisane dla tego obiektu">
                  {cooperation.filter((c) => c.node_id === index.id[node]).length === 0 ? (
                    <EmptyState text="Nie ma jeszcze działań dla tego obiektu." />
                  ) : (
                    <ul className="space-y-2">
                      {cooperation
                        .filter((c) => c.node_id === index.id[node])
                        .map((c) => (
                          <li key={c.id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs">
                            <span className="font-medium text-slate-900">{c.action_kind}</span>
                            <span className="mt-0.5 block text-slate-600">
                              termin: {c.due_date} · {c.action_id}
                            </span>
                            {c.note && <span className="mt-0.5 block text-slate-500">{c.note}</span>}
                          </li>
                        ))}
                    </ul>
                  )}
                </Panel>
              </div>
            </>
          )}

          <Panel
            title="Operatorzy z największymi lukami"
            subtitle="Kolejność według sumy braków, przy równych — według obsługiwanej ludności"
            right={
              <Button variant="ghost" onClick={exportOperators}>
                Pobierz CSV
              </Button>
            }
          >
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-white text-left text-slate-500">
                  <tr>
                    <th className="py-1.5 font-medium">Operator</th>
                    <th className="py-1.5 font-medium">Obiekty</th>
                    <th className="py-1.5 font-medium">Bez planu</th>
                    <th className="py-1.5 font-medium">Bez kontaktu</th>
                    <th className="py-1.5 font-medium">Bez umowy</th>
                    <th className="py-1.5 font-medium">Responsywność</th>
                  </tr>
                </thead>
                <tbody>
                  {operators.map((o) => (
                    <tr key={o.name} className="border-t border-slate-100">
                      <td className="py-1.5 truncate text-slate-900">{o.name}</td>
                      <td className="py-1.5 tabular-nums text-slate-600">{o.nodes}</td>
                      <td className="py-1.5 tabular-nums text-slate-600">{o.noPlan}</td>
                      <td className="py-1.5 tabular-nums text-slate-600">{o.noContact}</td>
                      <td className="py-1.5 tabular-nums text-slate-600">{o.noAgreement}</td>
                      <td className="py-1.5 tabular-nums text-slate-600">
                        {formatNumber(o.responsiveness, 1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>

      <Modal open={actionOpen} title="Działanie ze współpracy SPO-10" onClose={() => setActionOpen(false)}>
        <div className="space-y-3">
          <Field label="Rodzaj działania">
            <select
              className={inputClass}
              value={actionKind}
              onChange={(e) => setActionKind(e.target.value)}
            >
              {COOPERATION_ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Termin">
            <input
              className={inputClass}
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </Field>
          <Field label="Notatka">
            <textarea
              className={inputClass}
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </Field>
          {gaps.length > 0 && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              Podstawa działania zapisze się razem z rekordem: {gaps.join('; ')}.
            </p>
          )}
          {errors.length > 0 && (
            <ul className="space-y-1 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setActionOpen(false)}>Anuluj</Button>
            <Button variant="primary" onClick={() => void submit()}>
              Zapisz działanie
            </Button>
          </div>
        </div>
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
