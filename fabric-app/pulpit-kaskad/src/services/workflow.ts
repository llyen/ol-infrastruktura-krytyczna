import { getRayfinClient, isLocalBackend } from './rayfinClient';

/**
 * Zapis zwrotny pulpitu „Symulator kaskad IK".
 *
 * Zasady z `fabric-app/APP_SPEC.md`:
 * 1. Nic się nie usuwa. Zmiana decyzji o wzmocnieniu to nowy wpis wskazujący
 *    poprzedni — rejestr ma być dowodem, kto co wiedział i kiedy.
 * 2. **Operator IK nie widzi pełnego grafu zależności.** To nie jest kwestia
 *    wygody interfejsu: pełna mapa zależności krajowej infrastruktury
 *    krytycznej jest informacją, której nie udostępnia się szeroko.
 * 3. Meldunek operatora działa bez łączności. W scenariuszu, w którym pada
 *    zasilanie i łączność, operator z zalanego obiektu ma najgorsze warunki
 *    pracy w całym systemie — formularz musi to znieść.
 *
 * Bez skonfigurowanego backendu zapisy trafiają do pamięci, żeby aplikację
 * dało się zademonstrować bez połączenia z Fabric.
 */

export type UserRole =
  | 'RCB'
  | 'wojewoda / WCZK'
  | 'operator IK'
  | 'decydent'
  | 'audytor';

export const USER_ROLES: UserRole[] = [
  'RCB',
  'wojewoda / WCZK',
  'operator IK',
  'decydent',
  'audytor',
];

/** Role z pełnym obrazem krajowym. */
export const NATIONAL_ROLES: UserRole[] = ['RCB', 'decydent', 'audytor'];

/** Role uprawnione do zapisania scenariusza ćwiczebnego. */
export const SIMULATION_ROLES: UserRole[] = ['RCB', 'wojewoda / WCZK', 'decydent'];

/** Role uprawnione do zgłoszenia zapotrzebowania na paliwo. */
export const FUEL_ROLES: UserRole[] = ['RCB', 'wojewoda / WCZK'];

/** Role uprawnione do złożenia meldunku o obiekcie. */
export const REPORT_ROLES: UserRole[] = ['operator IK', 'wojewoda / WCZK'];

/** Role uprawnione do działań ze współpracy SPO-10. */
export const COOPERATION_ROLES: UserRole[] = ['RCB', 'wojewoda / WCZK'];

/** Role uprawnione do zatwierdzenia planu wzmocnień. */
export const HARDENING_ROLES: UserRole[] = ['decydent'];

export interface Actor {
  id: string;
  name: string;
  role: UserRole;
  /** Kod województwa; pusty = zakres krajowy. */
  voivodeshipCode: string;
  /** Nazwa operatora dla roli „operator IK" — ogranicza widok do własnych obiektów. */
  operatorName: string;
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
}

/* ------------------------------------------------------------------ */
/* Zakres widoczności                                                  */
/* ------------------------------------------------------------------ */

/**
 * Czy rola widzi pełny graf zależności między obiektami.
 *
 * Operator IK jest świadomie wykluczony. Widzi własne obiekty i skutki
 * ich awarii, ale nie to, kto jeszcze zależy od tych samych dostawców.
 */
export function canSeeDependencyGraph(role: UserRole): boolean {
  return role !== 'operator IK';
}

/** Czy rola widzi dane operacyjne obiektu (obciążenie, paliwo, meldunki). */
export function canSeeOperationalData(role: UserRole): boolean {
  return role !== 'decydent';
}

/** Czy rola może cokolwiek zapisać. Audytor ma wyłącznie odczyt. */
export function canWrite(role: UserRole): boolean {
  return role !== 'audytor';
}

/**
 * Czy aktor może działać na danym obiekcie. Reguły są tutaj, a nie
 * w komponencie, żeby dało się je sprawdzić testem bez renderowania ekranu.
 */
export function canActOn(
  actor: Actor,
  node: { voiv: string; operator: string },
): boolean {
  if (!canWrite(actor.role)) return false;
  if (actor.role === 'operator IK') return node.operator === actor.operatorName;
  if (actor.role === 'wojewoda / WCZK') {
    return !actor.voivodeshipCode || node.voiv === actor.voivodeshipCode;
  }
  return true;
}

/* ------------------------------------------------------------------ */
/* Słowniki                                                            */
/* ------------------------------------------------------------------ */

export const SIMULATION_MODES = ['awaria natychmiastowa', 'awaria zapowiedziana'] as const;
export type SimulationMode = (typeof SIMULATION_MODES)[number];

export const NODE_STATES = ['operational', 'degraded', 'down'] as const;
export type NodeState = (typeof NODE_STATES)[number];

export const STATE_LABELS: Record<NodeState, string> = {
  operational: 'sprawny',
  degraded: 'ograniczony',
  down: 'niedziałający',
};

export const EVENT_KINDS = [
  'zalanie obiektu',
  'utrata zasilania podstawowego',
  'awaria techniczna',
  'brak paliwa do agregatu',
  'utrata łączności',
  'ograniczenie przepustowości',
  'planowany wyłącznik',
] as const;

export const SUPPORT_KINDS = ['paliwo', 'pompy', 'transport', 'ochrona', 'łączność'] as const;
export type SupportKind = (typeof SUPPORT_KINDS)[number];

export const COOPERATION_ACTIONS = [
  'test kontaktu',
  'wniosek o wpis do rejestru IK',
  'zaplanowanie ćwiczenia',
  'wezwanie do aktualizacji planu ochrony',
] as const;
export type CooperationAction = (typeof COOPERATION_ACTIONS)[number];

/* ------------------------------------------------------------------ */
/* Rekordy                                                             */
/* ------------------------------------------------------------------ */

interface Authored {
  id: string;
  author_id: string;
  author_name: string;
  author_role: string;
  created_at: Date;
}

export interface ExerciseScenarioDraft {
  scene_time: string;
  seed_node_id: string;
  seed_node_name: string;
  voivodeship_code: string;
  mode: string;
  horizon_hours: number;
  assume_backups: boolean;
  nodes_failed: number;
  nodes_secondary: number;
  max_wave: number;
  affected_gminas: number;
  affected_population: number;
  k1_nodes_failed: number;
  first_secondary_hour: number;
  title: string;
  note: string;
}
export type ExerciseScenarioRecord = ExerciseScenarioDraft & Authored & { scenario_id: string };

export interface FuelRequestDraft {
  scene_time: string;
  node_id: string;
  node_name: string;
  voivodeship_code: string;
  gmina_code: string;
  operator_name: string;
  hours_remaining: number;
  litres_requested: number;
  priority: string;
  justification: string;
  status: string;
}
export type FuelRequestRecord = FuelRequestDraft & Authored & { request_id: string };

export interface OperatorReportDraft {
  scene_time: string;
  node_id: string;
  node_name: string;
  operator_name: string;
  voivodeship_code: string;
  event_kind: string;
  node_state: string;
  has_backup: boolean;
  fuel_hours: number;
  eta_restore_hours: number;
  support_requested: string;
  description: string;
  offline_sync_id: string;
  capture_mode: string;
}
export type OperatorReportRecord = OperatorReportDraft & Authored & { report_id: string };

export interface CooperationActionDraft {
  scene_time: string;
  node_id: string;
  node_name: string;
  operator_name: string;
  voivodeship_code: string;
  action_kind: string;
  gap_reason: string;
  due_date: string;
  note: string;
}
export type CooperationActionRecord = CooperationActionDraft & Authored & { action_id: string };

export interface HardeningDecisionDraft {
  scene_time: string;
  variant: string;
  node_ids: string;
  node_count: number;
  nodes_saved: number;
  population_saved: number;
  decision: string;
  justification: string;
  supersedes: string;
}
export type HardeningDecisionRecord = HardeningDecisionDraft & Authored & { decision_id: string };

/* ------------------------------------------------------------------ */
/* Walidacje                                                           */
/* ------------------------------------------------------------------ */

const MIN_JUSTIFICATION = 30;

export function validateScenario(
  draft: ExerciseScenarioDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!SIMULATION_ROLES.includes(actor.role)) {
    errors.push(`Rola „${actor.role}" nie zapisuje scenariuszy ćwiczebnych.`);
  }
  if (draft.title.trim().length < 5) {
    errors.push('Nazwa scenariusza musi mieć co najmniej 5 znaków.');
  }
  if (!draft.seed_node_id) errors.push('Wskaż obiekt inicjujący.');
  if (draft.horizon_hours < 6 || draft.horizon_hours > 240) {
    errors.push('Horyzont musi mieścić się w przedziale 6–240 h.');
  }
  return { ok: errors.length === 0, errors };
}

export function validateFuelRequest(
  draft: FuelRequestDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!FUEL_ROLES.includes(actor.role)) {
    errors.push(`Rola „${actor.role}" nie składa zapotrzebowania na paliwo.`);
  }
  if (!draft.node_id) errors.push('Wskaż obiekt.');
  if (draft.litres_requested <= 0) errors.push('Podaj dodatnią ilość paliwa.');
  if (draft.justification.trim().length < MIN_JUSTIFICATION) {
    errors.push(`Uzasadnienie musi mieć co najmniej ${MIN_JUSTIFICATION} znaków.`);
  }
  if (
    actor.role === 'wojewoda / WCZK' &&
    actor.voivodeshipCode &&
    draft.voivodeship_code !== actor.voivodeshipCode
  ) {
    errors.push('Obiekt leży poza województwem, w którym działasz.');
  }
  return { ok: errors.length === 0, errors };
}

export function validateOperatorReport(
  draft: OperatorReportDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!REPORT_ROLES.includes(actor.role)) {
    errors.push(`Rola „${actor.role}" nie składa meldunków o obiekcie.`);
  }
  if (actor.role === 'operator IK' && draft.operator_name !== actor.operatorName) {
    errors.push('Możesz meldować wyłącznie o obiektach własnego operatora.');
  }
  if (!draft.node_id) errors.push('Wskaż obiekt.');
  if (!draft.event_kind) errors.push('Wskaż rodzaj zdarzenia.');
  if (!NODE_STATES.includes(draft.node_state as NodeState)) {
    errors.push('Wskaż stan obiektu.');
  }
  // Stan inny niż sprawny bez informacji o rezerwie jest meldunkiem bezużytecznym:
  // sztab nie wie, czy ma godzinę czy dobę na reakcję.
  if (draft.node_state !== 'operational' && draft.has_backup && draft.fuel_hours <= 0) {
    errors.push('Podaj zapas paliwa dla zasilania rezerwowego.');
  }
  if (draft.node_state === 'down' && draft.eta_restore_hours <= 0) {
    errors.push('Podaj przewidywany czas przywrócenia.');
  }
  if (draft.description.length > 1000) {
    errors.push('Opis nie może przekraczać 1000 znaków.');
  }
  return { ok: errors.length === 0, errors };
}

export function validateCooperationAction(
  draft: CooperationActionDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!COOPERATION_ROLES.includes(actor.role)) {
    errors.push(`Rola „${actor.role}" nie inicjuje działań ze współpracy SPO-10.`);
  }
  if (!draft.node_id) errors.push('Wskaż obiekt.');
  if (!COOPERATION_ACTIONS.includes(draft.action_kind as CooperationAction)) {
    errors.push('Wskaż rodzaj działania.');
  }
  if (!draft.due_date) errors.push('Podaj termin.');
  return { ok: errors.length === 0, errors };
}

export function validateHardeningDecision(
  draft: HardeningDecisionDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!HARDENING_ROLES.includes(actor.role)) {
    errors.push(`Rola „${actor.role}" nie zatwierdza planu wzmocnień.`);
  }
  if (draft.node_count === 0) errors.push('Koszyk jest pusty.');
  if (draft.justification.trim().length < MIN_JUSTIFICATION) {
    errors.push(`Uzasadnienie musi mieć co najmniej ${MIN_JUSTIFICATION} znaków.`);
  }
  return { ok: errors.length === 0, errors };
}

/* ------------------------------------------------------------------ */
/* Tryb terenowy                                                       */
/* ------------------------------------------------------------------ */

/**
 * Scala meldunki wysłane wielokrotnie po odzyskaniu łączności.
 *
 * Urządzenie nadaje identyfikator synchronizacji przed wysyłką. Ta sama paczka
 * wysłana ponownie nie może utworzyć drugiego meldunku — zostaje najnowszy
 * zapis dla danego identyfikatora. Zapisy bez identyfikatora nie są scalane,
 * bo to niezależne meldunki złożone online.
 */
export function dedupeReports<T extends { offline_sync_id: string; created_at: Date }>(
  rows: T[],
): T[] {
  const newest = new Map<string, T>();
  const standalone: T[] = [];
  for (const row of rows) {
    if (!row.offline_sync_id) {
      standalone.push(row);
      continue;
    }
    const current = newest.get(row.offline_sync_id);
    if (!current || row.created_at.getTime() > current.created_at.getTime()) {
      newest.set(row.offline_sync_id, row);
    }
  }
  return [...standalone, ...newest.values()];
}

/* ------------------------------------------------------------------ */
/* Podpowiedzi operacyjne                                              */
/* ------------------------------------------------------------------ */

/**
 * Ile litrów paliwa trzeba, żeby obiekt dotrwał do podanej godziny.
 * Przyjęte 42 l/h to typowe zużycie agregatu średniej mocy — wartość
 * demonstracyjna, ale rzędu wielkości, w którym decyzja ma sens.
 */
export const LITRES_PER_HOUR = 42;

export function suggestedLitres(hoursRemaining: number, targetHours: number): number {
  const gap = Math.max(0, targetHours - hoursRemaining);
  return Math.ceil((gap * LITRES_PER_HOUR) / 50) * 50;
}

/** Próg, poniżej którego zapas paliwa wymaga natychmiastowej reakcji. */
export const FUEL_URGENT_H = 6;

export function fuelPriority(hoursRemaining: number, critClass: string): string {
  if (hoursRemaining < FUEL_URGENT_H || critClass === 'K1') return 'pilny';
  if (hoursRemaining < 12) return 'podwyższony';
  return 'zwykły';
}

/** Braki we współpracy SPO-10 opisane słowami, nie flagami. */
export function cooperationGaps(node: {
  planStatus: string;
  hasContact: number;
  hasAgreement: number;
  onRegister: number;
  lastContactTest: string;
}): string[] {
  const gaps: string[] = [];
  if (!node.onRegister) gaps.push('obiekt poza rejestrem IK');
  if (node.planStatus !== 'zatwierdzony') gaps.push(`plan ochrony: ${node.planStatus}`);
  if (!node.hasContact) gaps.push('brak punktu kontaktowego');
  if (!node.hasAgreement) gaps.push('brak umowy o wymianie danych');
  if (node.lastContactTest) {
    const days = (Date.now() - new Date(node.lastContactTest).getTime()) / 86_400_000;
    if (days > 365) gaps.push('test kontaktu starszy niż rok');
  } else {
    gaps.push('brak testu kontaktu');
  }
  return gaps;
}

/* ------------------------------------------------------------------ */
/* Zapis                                                               */
/* ------------------------------------------------------------------ */

const memory = {
  scenarios: [] as ExerciseScenarioRecord[],
  fuel: [] as FuelRequestRecord[],
  reports: [] as OperatorReportRecord[],
  cooperation: [] as CooperationActionRecord[],
  hardening: [] as HardeningDecisionRecord[],
};

const AUTHOR_COLS = ['author_id', 'author_name', 'author_role', 'created_at'] as const;

const SCENARIO_COLS = [
  'id', 'scenario_id', 'scene_time', 'seed_node_id', 'seed_node_name',
  'voivodeship_code', 'mode', 'horizon_hours', 'assume_backups',
  'nodes_failed', 'nodes_secondary', 'max_wave', 'affected_gminas',
  'affected_population', 'k1_nodes_failed', 'first_secondary_hour',
  'title', 'note', ...AUTHOR_COLS,
] as const;

const FUEL_COLS = [
  'id', 'request_id', 'scene_time', 'node_id', 'node_name', 'voivodeship_code',
  'gmina_code', 'operator_name', 'hours_remaining', 'litres_requested',
  'priority', 'justification', 'status', ...AUTHOR_COLS,
] as const;

const REPORT_COLS = [
  'id', 'report_id', 'scene_time', 'node_id', 'node_name', 'operator_name',
  'voivodeship_code', 'event_kind', 'node_state', 'has_backup', 'fuel_hours',
  'eta_restore_hours', 'support_requested', 'description', 'offline_sync_id',
  'capture_mode', ...AUTHOR_COLS,
] as const;

const COOPERATION_COLS = [
  'id', 'action_id', 'scene_time', 'node_id', 'node_name', 'operator_name',
  'voivodeship_code', 'action_kind', 'gap_reason', 'due_date', 'note',
  ...AUTHOR_COLS,
] as const;

const HARDENING_COLS = [
  'id', 'decision_id', 'scene_time', 'variant', 'node_ids', 'node_count',
  'nodes_saved', 'population_saved', 'decision', 'justification', 'supersedes',
  ...AUTHOR_COLS,
] as const;

/* eslint-disable @typescript-eslint/no-explicit-any */
async function readAll<T>(
  entityName: string,
  cols: readonly string[],
  fallback: T[],
): Promise<T[]> {
  if (isLocalBackend()) return [...fallback];
  const client = getRayfinClient() as any;
  const rows = await client.data[entityName]
    .select([...cols])
    .orderBy({ created_at: 'desc' })
    .execute();
  return rows as T[];
}

async function writeOne<T extends { id: string }>(
  entityName: string,
  record: T,
  fallback: T[],
): Promise<T> {
  if (isLocalBackend()) {
    fallback.unshift(record);
    return record;
  }
  const client = getRayfinClient() as any;
  const { id: _ignored, ...payload } = record;
  void _ignored;
  const saved = await client.data[entityName].create(payload);
  return saved as T;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

let counter = 0;

function newId(prefix: string, sceneTime: string): string {
  counter += 1;
  const stamp = sceneTime.replace(/[^0-9]/g, '').slice(4, 12) || '00000000';
  return `${prefix}-${stamp}-${String(counter).padStart(3, '0')}`;
}

function authored(actor: Actor): Omit<Authored, 'id'> {
  return {
    author_id: actor.id,
    author_name: actor.name,
    author_role: actor.role,
    created_at: new Date(),
  };
}

export const listScenarios = () =>
  readAll<ExerciseScenarioRecord>('ExerciseScenario', SCENARIO_COLS, memory.scenarios);
export const listFuelRequests = () =>
  readAll<FuelRequestRecord>('FuelRequest', FUEL_COLS, memory.fuel);
export const listOperatorReports = () =>
  readAll<OperatorReportRecord>('OperatorReport', REPORT_COLS, memory.reports);
export const listCooperationActions = () =>
  readAll<CooperationActionRecord>('CooperationAction', COOPERATION_COLS, memory.cooperation);
export const listHardeningDecisions = () =>
  readAll<HardeningDecisionRecord>('HardeningDecision', HARDENING_COLS, memory.hardening);

export async function saveScenario(
  draft: ExerciseScenarioDraft,
  actor: Actor,
): Promise<ExerciseScenarioRecord> {
  const v = validateScenario(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: ExerciseScenarioRecord = {
    ...draft,
    title: draft.title.trim(),
    note: draft.note.trim(),
    id: crypto.randomUUID(),
    scenario_id: newId('SYM', draft.scene_time),
    ...authored(actor),
  };
  return writeOne('ExerciseScenario', record, memory.scenarios);
}

export async function saveFuelRequest(
  draft: FuelRequestDraft,
  actor: Actor,
): Promise<FuelRequestRecord> {
  const v = validateFuelRequest(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: FuelRequestRecord = {
    ...draft,
    justification: draft.justification.trim(),
    id: crypto.randomUUID(),
    request_id: newId('PAL', draft.scene_time),
    ...authored(actor),
  };
  return writeOne('FuelRequest', record, memory.fuel);
}

export async function saveOperatorReport(
  draft: OperatorReportDraft,
  actor: Actor,
): Promise<OperatorReportRecord> {
  const v = validateOperatorReport(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: OperatorReportRecord = {
    ...draft,
    description: draft.description.trim(),
    offline_sync_id: draft.offline_sync_id || crypto.randomUUID(),
    id: crypto.randomUUID(),
    report_id: newId('MEL', draft.scene_time),
    ...authored(actor),
  };
  return writeOne('OperatorReport', record, memory.reports);
}

export async function saveCooperationAction(
  draft: CooperationActionDraft,
  actor: Actor,
): Promise<CooperationActionRecord> {
  const v = validateCooperationAction(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: CooperationActionRecord = {
    ...draft,
    note: draft.note.trim(),
    id: crypto.randomUUID(),
    action_id: newId('WSP', draft.scene_time),
    ...authored(actor),
  };
  return writeOne('CooperationAction', record, memory.cooperation);
}

export async function saveHardeningDecision(
  draft: HardeningDecisionDraft,
  actor: Actor,
): Promise<HardeningDecisionRecord> {
  const v = validateHardeningDecision(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: HardeningDecisionRecord = {
    ...draft,
    justification: draft.justification.trim(),
    id: crypto.randomUUID(),
    decision_id: newId('WZM', draft.scene_time),
    ...authored(actor),
  };
  return writeOne('HardeningDecision', record, memory.hardening);
}
