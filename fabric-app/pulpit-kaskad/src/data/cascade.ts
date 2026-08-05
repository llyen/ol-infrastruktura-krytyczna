/**
 * Silnik propagacji kaskady awarii — port `cascade_engine.py`.
 *
 * Liczy w przeglądarce, nie na serwerze. Powód jest merytoryczny, nie techniczny:
 * użytkownik ma wskazać **dowolny** obiekt i natychmiast zobaczyć skutki, a także
 * przestawić założenie („wszystkie agregaty sprawne") i zobaczyć różnicę. Zestaw
 * wyliczony z góry nie pokryłby ani 2106 możliwych punktów startu, ani przełączników.
 *
 * Model (identyczny z notatnikami 02–04):
 *  - węzeł przestaje działać, gdy suma udziałów utraconych wejść przekroczy próg,
 *  - każda zależność ma opóźnienie technologiczne (`lagHours`),
 *  - zależności zasilające są dodatkowo opóźnione o autonomię rezerwy,
 *  - **jeśli rezerwa odbiorcy jest dłuższa niż czas odtworzenia dostawcy, odbiorca
 *    nie pada wcale** — agregat przykrywa całą przerwę. To właśnie czyni z autonomii
 *    dźwignię inwestycyjną, a nie tylko odroczenie skutku,
 *  - redundancja `full` przenosi jedynie ułamek udziału (automatyczne przełączenie).
 *
 * Kolejka priorytetowa po czasie daje przyczynowo poprawną i powtarzalną kolejność.
 */

import type { SceneIndex } from './model';

const POWER_DEPS = new Set(['electricity', 'generation']);
const FUEL_DEPS = new Set(['fuel']);

export const FULL_REDUNDANCY_FACTOR = 0.4;
export const PARTIAL_REDUNDANCY_FACTOR = 0.9;
export const DEFAULT_THRESHOLD = 0.5;
export const DEFAULT_HORIZON_H = 240;

export interface CascadeEvent {
  node: number;
  failHour: number;
  wave: number;
  causeNode: number | null;
  dependency: string;
}

export interface CascadeOptions {
  /** Godzina awarii każdego z obiektów inicjujących (0 = moment zdarzenia). */
  seeds: Map<number, number>;
  horizonHours?: number;
  threshold?: number;
  /** Godziny autonomii dołożone wybranym węzłom — scenariusze wzmocnień. */
  autonomyBonus?: Map<number, number>;
  /** „Wszystkie agregaty sprawne" — założenie planistyczne, nie stan faktyczny. */
  assumeAllBackupsWork?: boolean;
}

export interface CascadeResult {
  events: CascadeEvent[];
  /** Węzły uratowane przez rezerwę zasilania — dowód wartości autonomii. */
  saved: Set<number>;
  nodesFailed: number;
  nodesSecondary: number;
  maxWave: number;
  firstSecondaryHour: number;
  affectedGminas: Set<string>;
  affectedPopulation: number;
  k1Failed: number;
  bySystemGroup: Map<string, number>;
  bySystem: Map<string, number>;
}

/**
 * Kopiec binarny uporządkowany po czasie awarii.
 *
 * Sortowanie tablicy po każdym wstawieniu dawałoby ten sam wynik, ale przy 6552
 * krawędziach i przeliczaniu na każde przesunięcie suwaka byłoby odczuwalne.
 * Drugi klucz (kolejność wstawienia) usuwa niejednoznaczność przy równych czasach,
 * dzięki czemu ten sam wybór zawsze daje ten sam przebieg.
 */
class TimeQueue {
  private heap: Array<[number, number, number, number | null, string, number]> = [];
  private seq = 0;

  push(time: number, node: number, cause: number | null, dep: string, wave: number): void {
    this.seq += 1;
    this.heap.push([time, this.seq, node, cause, dep, wave]);
    let i = this.heap.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.less(i, parent)) {
        this.swap(i, parent);
        i = parent;
      } else break;
    }
  }

  pop(): [number, number, number, number | null, string, number] | undefined {
    if (this.heap.length === 0) return undefined;
    const top = this.heap[0];
    const last = this.heap.pop()!;
    if (this.heap.length > 0) {
      this.heap[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let small = i;
        if (l < this.heap.length && this.less(l, small)) small = l;
        if (r < this.heap.length && this.less(r, small)) small = r;
        if (small === i) break;
        this.swap(i, small);
        i = small;
      }
    }
    return top;
  }

  private less(a: number, b: number): boolean {
    const x = this.heap[a];
    const y = this.heap[b];
    return x[0] !== y[0] ? x[0] < y[0] : x[1] < y[1];
  }

  private swap(a: number, b: number): void {
    const t = this.heap[a];
    this.heap[a] = this.heap[b];
    this.heap[b] = t;
  }
}

function edgeFactor(redundancy: string): number {
  if (redundancy === 'full') return FULL_REDUNDANCY_FACTOR;
  if (redundancy === 'partial') return PARTIAL_REDUNDANCY_FACTOR;
  return 1;
}

function bufferHours(idx: SceneIndex, node: number, dep: string): number {
  const autonomy = idx.autonomyH[node];
  const fuel = idx.fuelH[node];
  if (POWER_DEPS.has(dep)) {
    const backup = idx.backupType[node];
    if (backup === 'genset' || backup === 'onsite_fuel') {
      return Math.min(autonomy, fuel || autonomy);
    }
    return autonomy;
  }
  if (FUEL_DEPS.has(dep)) return fuel;
  return 0;
}

export function simulate(idx: SceneIndex, options: CascadeOptions): CascadeResult {
  const horizon = options.horizonHours ?? DEFAULT_HORIZON_H;
  const threshold = options.threshold ?? DEFAULT_THRESHOLD;
  const bonus = options.autonomyBonus;
  const assumeBackups = options.assumeAllBackupsWork ?? false;

  const lost = new Float64Array(idx.count);
  const failedAt = new Float64Array(idx.count).fill(-1);
  const saved = new Set<number>();
  const events: CascadeEvent[] = [];
  const queue = new TimeQueue();

  for (const [node, time] of [...options.seeds].sort((a, b) => a[0] - b[0])) {
    queue.push(time, node, null, 'seed', 0);
  }

  for (;;) {
    const item = queue.pop();
    if (!item) break;
    const [t, , node, cause, dep, wave] = item;
    if (failedAt[node] >= 0 || t > horizon) continue;
    failedAt[node] = t;
    events.push({ node, failHour: Math.round(t * 100) / 100, wave, causeNode: cause, dependency: dep });

    const start = idx.edgeStart[node];
    const end = idx.edgeStart[node + 1];
    for (let e = start; e < end; e += 1) {
      const target = idx.edgeTarget[e];
      if (failedAt[target] >= 0) continue;
      lost[target] += idx.edgeImpact[e] * edgeFactor(idx.edgeRedundancy[e]);
      if (lost[target] < threshold) continue;

      const depType = idx.edgeDependency[e];
      let buffer = bufferHours(idx, target, depType) + (bonus?.get(target) ?? 0);
      // Założenie planistyczne: agregat, który istnieje, na pewno zadziała.
      // Bez tego przełącznika demonstracja nie odróżnia braku rezerwy
      // od rezerwy niesprawnej, a to dwa różne problemy i dwa różne budżety.
      if (assumeBackups && buffer === 0 && idx.backupType[target] !== 'none') {
        buffer = idx.autonomyH[target] || 8;
      }

      if (buffer > 0 && buffer >= idx.restoreH[node]) {
        saved.add(target);
        continue;
      }
      const failAt = t + idx.edgeLag[e] + buffer;
      if (failAt > horizon) continue;
      queue.push(failAt, target, node, depType, wave + 1);
    }
  }

  return summarize(idx, events, saved);
}

function summarize(idx: SceneIndex, events: CascadeEvent[], saved: Set<number>): CascadeResult {
  const SERVICE_GROUPS = new Set(['energy', 'water', 'health']);
  const gminas = new Set<string>();
  const byGroup = new Map<string, number>();
  const bySystem = new Map<string, number>();
  let secondary = 0;
  let maxWave = 0;
  let firstSecondary = Number.POSITIVE_INFINITY;
  let k1 = 0;

  for (const e of events) {
    const group = idx.group[e.node];
    byGroup.set(group, (byGroup.get(group) ?? 0) + 1);
    const sys = idx.systemCode[e.node];
    bySystem.set(sys, (bySystem.get(sys) ?? 0) + 1);
    if (SERVICE_GROUPS.has(group)) gminas.add(idx.gmina[e.node]);
    if (e.wave > 0) {
      secondary += 1;
      if (e.failHour < firstSecondary) firstSecondary = e.failHour;
    }
    if (e.wave > maxWave) maxWave = e.wave;
    if (idx.critClass[e.node] === 'K1') k1 += 1;
  }

  // Ludność liczona po gminach, nie przez sumowanie `population_served`.
  // Ten drugi sposób liczy tę samą osobę raz na każdy system, który ją obsługuje,
  // i potrafi dać liczbę większą niż ludność Polski.
  let population = 0;
  for (const g of gminas) population += idx.gminaPopulation[g] ?? 0;

  return {
    events,
    saved,
    nodesFailed: events.length,
    nodesSecondary: secondary,
    maxWave,
    firstSecondaryHour: Number.isFinite(firstSecondary) ? firstSecondary : 0,
    affectedGminas: gminas,
    affectedPopulation: population,
    k1Failed: k1,
    bySystemGroup: byGroup,
    bySystem,
  };
}

/** Skutki w pierwszych `hours` godzinach — zanim sztab zdąży się zebrać. */
export function firstHours(result: CascadeResult, hours: number): CascadeEvent[] {
  return result.events.filter((e) => e.failHour <= hours);
}

/** Drzewo skutków: dzieci każdego węzła w kolejności wystąpienia. */
export function effectTree(result: CascadeResult): Map<number | null, CascadeEvent[]> {
  const tree = new Map<number | null, CascadeEvent[]>();
  for (const e of result.events) {
    const list = tree.get(e.causeNode);
    if (list) list.push(e);
    else tree.set(e.causeNode, [e]);
  }
  return tree;
}
