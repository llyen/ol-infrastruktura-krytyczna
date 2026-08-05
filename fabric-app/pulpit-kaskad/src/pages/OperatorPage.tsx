import { useMemo, useState } from 'react';

import {
  Badge,
  Button,
  EmptyState,
  Field,
  Panel,
  Toast,
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
  EVENT_KINDS,
  NODE_STATES,
  REPORT_ROLES,
  STATE_LABELS,
  SUPPORT_KINDS,
  dedupeReports,
  saveOperatorReport,
  validateOperatorReport,
  type NodeState,
  type OperatorReportDraft,
} from '@/services/workflow';

const timeFormat = new Intl.DateTimeFormat('pl-PL', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

function emptyDraft(sceneTime: string): OperatorReportDraft {
  return {
    scene_time: sceneTime,
    node_id: '',
    node_name: '',
    operator_name: '',
    voivodeship_code: '',
    event_kind: '',
    node_state: 'degraded',
    has_backup: false,
    fuel_hours: 0,
    eta_restore_hours: 0,
    support_requested: '',
    description: '',
    offline_sync_id: '',
    capture_mode: 'online',
  };
}

export function OperatorPage() {
  const { index, loading, error, frame, actor, offline, reports, refresh } = useScenario();
  const [draft, setDraft] = useState<OperatorReportDraft | null>(null);
  const [queue, setQueue] = useState<OperatorReportDraft[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  /** Obiekty, o których wolno meldować: operator IK tylko własne, wojewoda — swoje województwo. */
  const scope = useMemo(() => {
    if (!index) return [];
    const out: number[] = [];
    for (let i = 0; i < index.count; i += 1) {
      if (actor.role === 'operator IK') {
        if (!actor.operatorName || index.operator[i] !== actor.operatorName) continue;
      } else if (actor.voivodeshipCode && index.voiv[i] !== actor.voivodeshipCode) continue;
      out.push(i);
      if (out.length >= 400) break;
    }
    return out;
  }, [index, actor.role, actor.operatorName, actor.voivodeshipCode]);

  /** Meldunki z bazy aplikacji — scalone po identyfikatorze synchronizacji. */
  const mine = useMemo(() => {
    const rows = dedupeReports(
      reports.map((r) => ({ ...r, created_at: new Date(r.created_at) })),
    );
    return rows
      .filter((r) =>
        actor.role === 'operator IK' && actor.operatorName
          ? r.operator_name === actor.operatorName
          : true,
      )
      .sort((a, b) => b.created_at.getTime() - a.created_at.getTime())
      .slice(0, 40);
  }, [reports, actor.role, actor.operatorName]);

  /** Strumień meldunków ze sceny — tło, na którym widać, że kanał żyje. */
  const feed = useMemo(() => {
    if (!index) return [];
    return index.reports
      .filter((r) =>
        actor.role === 'operator IK' && actor.operatorName
          ? index.operator[r.node] === actor.operatorName
          : !actor.voivodeshipCode || index.voiv[r.node] === actor.voivodeshipCode,
      )
      .slice(-40)
      .reverse();
  }, [index, actor.role, actor.operatorName, actor.voivodeshipCode]);

  if (loading) return <EmptyState text="Wczytywanie danych operatora…" />;
  if (error) return <EmptyState text={error} />;
  if (!index) return null;

  const sceneTime = frameTime(index.scene.meta, frame).toISOString();
  const allowed = REPORT_ROLES.includes(actor.role);
  const current = draft ?? emptyDraft(sceneTime);
  const set = (patch: Partial<OperatorReportDraft>) =>
    setDraft({ ...current, ...patch, scene_time: sceneTime });

  const pickNode = (id: string) => {
    const i = index.byId.get(id);
    if (i === undefined) {
      set({ node_id: '', node_name: '' });
      return;
    }
    set({
      node_id: id,
      node_name: index.name[i],
      operator_name: index.operator[i],
      voivodeship_code: index.voiv[i],
      has_backup: index.backupType[i] !== 'none',
      fuel_hours: Math.round(index.fuelH[i] * 10) / 10,
    });
  };

  const submit = async () => {
    const payload: OperatorReportDraft = {
      ...current,
      scene_time: sceneTime,
      capture_mode: offline ? 'terenowy' : 'online',
      offline_sync_id: current.offline_sync_id || (offline ? crypto.randomUUID() : ''),
    };
    const v = validateOperatorReport(payload, actor);
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    if (offline) {
      setQueue((q) => [...q, payload]);
      setDraft(null);
      setErrors([]);
      setToast('Meldunek zapisany lokalnie. Wyśle się po odzyskaniu łączności.');
      return;
    }
    try {
      await saveOperatorReport(payload, actor);
      await refresh();
      setDraft(null);
      setErrors([]);
      setToast('Meldunek przyjęty. Trafia do obrazu sytuacyjnego sztabu.');
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  /**
   * Wysyłka kolejki terenowej.
   *
   * Meldunki idą z tym samym identyfikatorem synchronizacji, z jakim zostały
   * zapisane w terenie. Ponowna wysyłka tej samej paczki nie utworzy drugiego
   * meldunku — `dedupeReports` zostawi najnowszy zapis dla identyfikatora.
   */
  const sync = async () => {
    setSending(true);
    let sent = 0;
    try {
      for (const item of queue) {
        await saveOperatorReport(item, actor);
        sent += 1;
      }
      setQueue([]);
      await refresh();
      setToast(`Zsynchronizowano ${formatNumber(sent)} meldunków.`);
    } catch (e: unknown) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-4">
      {!allowed && (
        <Panel title="Brak uprawnień" tone="accent">
          <p className="text-sm text-slate-600">
            Meldunek o obiekcie składa operator IK albo wojewódzkie centrum zarządzania
            kryzysowego. Przełącz rolę w pasku u góry, żeby zobaczyć formularz.
          </p>
        </Panel>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        {allowed && (
          <Panel
            title="Meldunek o obiekcie"
            subtitle={
              offline
                ? 'Tryb terenowy — zapis lokalny z identyfikatorem synchronizacji'
                : 'Zapis trafia bezpośrednio do obrazu sytuacyjnego'
            }
            tone={offline ? 'accent' : 'default'}
          >
            <div className="space-y-3">
              <Field
                label="Obiekt"
                hint={
                  actor.role === 'operator IK'
                    ? 'Lista zawiera wyłącznie obiekty Twojego operatora.'
                    : 'Lista ograniczona do Twojego województwa.'
                }
              >
                <select
                  className={inputClass}
                  value={current.node_id}
                  onChange={(e) => pickNode(e.target.value)}
                >
                  <option value="">— wskaż obiekt —</option>
                  {scope.map((i) => (
                    <option key={index.id[i]} value={index.id[i]}>
                      {shortNodeName(index.name[i])} ·{' '}
                      {shortGminaName(index.gminaNames[index.gmina[i]] ?? index.gmina[i])}
                    </option>
                  ))}
                </select>
              </Field>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Rodzaj zdarzenia">
                  <select
                    className={inputClass}
                    value={current.event_kind}
                    onChange={(e) => set({ event_kind: e.target.value })}
                  >
                    <option value="">— wskaż —</option>
                    {EVENT_KINDS.map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Stan obiektu">
                  <select
                    className={inputClass}
                    value={current.node_state}
                    onChange={(e) => set({ node_state: e.target.value as NodeState })}
                  >
                    {NODE_STATES.map((s) => (
                      <option key={s} value={s}>
                        {STATE_LABELS[s]}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={current.has_backup}
                  onChange={(e) => set({ has_backup: e.target.checked })}
                  className="accent-gov"
                />
                Obiekt pracuje na zasilaniu rezerwowym
              </label>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field
                  label="Zapas paliwa (h)"
                  hint="Bez tej liczby sztab nie wie, czy ma godzinę czy dobę."
                >
                  <input
                    className={inputClass}
                    type="number"
                    min={0}
                    step={0.5}
                    value={current.fuel_hours}
                    onChange={(e) => set({ fuel_hours: Number(e.target.value) })}
                    disabled={!current.has_backup}
                  />
                </Field>
                <Field label="Przewidywane przywrócenie (h)">
                  <input
                    className={inputClass}
                    type="number"
                    min={0}
                    step={0.5}
                    value={current.eta_restore_hours}
                    onChange={(e) => set({ eta_restore_hours: Number(e.target.value) })}
                  />
                </Field>
              </div>

              <Field label="Wnioskowane wsparcie">
                <select
                  className={inputClass}
                  value={current.support_requested}
                  onChange={(e) => set({ support_requested: e.target.value })}
                >
                  <option value="">— nie wnioskuję —</option>
                  {SUPPORT_KINDS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Opis" hint="Do 1000 znaków">
                <textarea
                  className={inputClass}
                  rows={3}
                  value={current.description}
                  onChange={(e) => set({ description: e.target.value })}
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
                <Button onClick={() => setDraft(null)}>Wyczyść</Button>
                <Button variant="primary" onClick={() => void submit()}>
                  {offline ? 'Zapisz w terenie' : 'Złóż meldunek'}
                </Button>
              </div>
            </div>
          </Panel>
        )}

        <div className="space-y-4">
          {queue.length > 0 && (
            <Panel
              title="Kolejka terenowa"
              subtitle="Meldunki czekające na łączność"
              tone="accent"
              right={
                <Button variant="primary" onClick={() => void sync()} disabled={sending || offline}>
                  {offline ? 'Wyłącz tryb terenowy, aby wysłać' : `Synchronizuj (${queue.length})`}
                </Button>
              }
            >
              <ul className="space-y-2">
                {queue.map((q) => (
                  <li
                    key={q.offline_sync_id}
                    className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700"
                  >
                    <span className="font-medium text-slate-900">
                      {shortNodeName(q.node_name)}
                    </span>{' '}
                    · {q.event_kind} · {STATE_LABELS[q.node_state as NodeState]}
                    <span className="mt-0.5 block text-slate-500">
                      identyfikator synchronizacji: {q.offline_sync_id.slice(0, 8)}
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Złożone meldunki" subtitle="Zapisy z bazy aplikacji, po scaleniu duplikatów">
            {mine.length === 0 ? (
              <EmptyState text="Nie ma jeszcze meldunków złożonych w tej sesji." />
            ) : (
              <div className="max-h-72 space-y-2 overflow-y-auto">
                {mine.map((r) => (
                  <div key={r.id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium text-slate-900">
                        {shortNodeName(r.node_name)}
                      </span>
                      <Badge
                        className={
                          r.node_state === 'down'
                            ? 'bg-red-50 text-red-700 ring-red-600/20'
                            : r.node_state === 'degraded'
                              ? 'bg-amber-50 text-amber-700 ring-amber-600/20'
                              : 'bg-green-50 text-green-800 ring-green-600/20'
                        }
                      >
                        {STATE_LABELS[r.node_state as NodeState]}
                      </Badge>
                    </div>
                    <p className="mt-0.5 text-slate-600">
                      {r.event_kind}
                      {r.has_backup && ` · rezerwa ${formatHours(r.fuel_hours)}`}
                      {r.support_requested && ` · wsparcie: ${r.support_requested}`}
                    </p>
                    <p className="mt-0.5 text-slate-500">
                      {r.report_id} · {timeFormat.format(new Date(r.created_at))} ·{' '}
                      {r.capture_mode}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title="Strumień meldunków ze zdarzenia"
            subtitle="Tło operacyjne — zgłoszenia napływające kanałami operatorów"
          >
            {feed.length === 0 ? (
              <EmptyState text="Brak meldunków w tym zakresie." />
            ) : (
              <div className="max-h-72 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-white text-left text-slate-500">
                    <tr>
                      <th className="py-1.5 font-medium">Czas</th>
                      <th className="py-1.5 font-medium">Obiekt</th>
                      <th className="py-1.5 font-medium">Zgłoszenie</th>
                      <th className="py-1.5 font-medium">Kanał</th>
                    </tr>
                  </thead>
                  <tbody>
                    {feed.map((r, i) => (
                      <tr key={`${r.time}-${r.node}-${i}`} className="border-t border-slate-100">
                        <td className="py-1.5 whitespace-nowrap text-slate-600">
                          {timeFormat.format(new Date(r.time))}
                        </td>
                        <td className="py-1.5 truncate text-slate-900">
                          {shortNodeName(index.name[r.node])}
                          <span className="ml-1 text-slate-500">
                            ({groupLabel(index.group[r.node])})
                          </span>
                        </td>
                        <td className="py-1.5 text-slate-600">
                          {r.kind}
                          {r.support ? ' · wnioskuje o wsparcie' : ''}
                        </td>
                        <td className="py-1.5 text-slate-500">{r.channel}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      </div>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
