/**
 * Model sceny „Symulator kaskad IK".
 *
 * Scena przychodzi kolumnowo (tablice tablic), bo forma obiektowa dla 6552
 * krawędzi to kilkukrotnie więcej bajtów na te same dane. `indexScene` rozkłada
 * ją raz na tablice typowane i listę sąsiedztwa w formacie CSR, dzięki czemu
 * symulacja nie alokuje pamięci w pętli i nadąża za suwakiem horyzontu.
 */

/* ------------------------------------------------------------------ */
/* Typy sceny                                                          */
/* ------------------------------------------------------------------ */

export interface SceneMeta {
  generatedBy: string;
  nodeCount: number;
  edgeCount: number;
  floodStart: string;
  floodFrames: number;
  frameHours: number;
  headline: {
    trigger_node_id: string;
    trigger_node_name: string;
    trigger_node_type: string;
    trigger_gmina: string;
    people_without_power: number;
    secondary_nodes: number;
    max_wave: number;
    hospitals_affected: number;
    hospitals_on_gensets: number;
    hospitals_without_backup: number;
    hospital_median_autonomy_h: number;
    water_nodes_affected: number;
    hours_until_water_stops: number;
    telecom_nodes_affected: number;
    rescue_nodes_affected: number;
    first_secondary_hour: number;
  };
  floodScenario: {
    nodes_failed_total: number;
    nodes_failed_secondary: number;
    max_wave: number;
    affected_gminas: number;
    affected_population: number;
    k1_nodes_failed: number;
    flooded_nodes: number;
    amplification_ratio: number;
  };
  worstSingleNode: {
    node_id: string;
    node_name: string;
    nodes_failed_total: number;
    affected_population: number;
  };
}

export interface SystemInfo {
  code: string;
  name: string;
  group: string;
  department: string;
  spo: string;
}

export interface SystemStat {
  code: string;
  nodes: number;
  k1: number;
  avgAutonomyH: number;
  noBackup: number;
  singleSourcePower: number;
  onRegisterPct: number;
}

export interface Variant {
  variant: string;
  description: string;
  hardenedNodes: number;
  newFeeds: number;
  nodesFailed: number;
  nodesSecondary: number;
  maxWave: number;
  gminas: number;
  population: number;
  k1Failed: number;
  secondaryReductionPct: number;
  populationReductionPct: number;
}

export interface OperatorGap {
  name: string;
  nodes: number;
  noPlan: number;
  noContact: number;
  noAgreement: number;
  pop: number;
  responsiveness: number;
}

export interface Scene {
  meta: SceneMeta;
  nodeFields: string[];
  nodes: unknown[][];
  edgeFields: string[];
  edges: unknown[][];
  systems: SystemInfo[];
  systemStats: SystemStat[];
  voivodeships: { code: string; name: string }[];
  gminaNames: Record<string, string>;
  gminaPopulation: Record<string, number>;
  floodFrames: number[][][];
  reportFields: string[];
  reports: unknown[][];
  topCascade: {
    node: number;
    cascadeIndex: number;
    nodes: number;
    population: number;
    systems: number;
    tier: string;
    firstSecondaryHour: number;
  }[];
  spof: {
    node: number;
    fragility: number;
    reason: string;
    cascadeNodes: number;
    cascadePopulation: number;
  }[];
  variants: Variant[];
  marginalFields: string[];
  marginal: number[][];
  operators: OperatorGap[];
}

/* ------------------------------------------------------------------ */
/* Indeks                                                              */
/* ------------------------------------------------------------------ */

export interface OperatorReport {
  time: string;
  node: number;
  kind: string;
  severity: string;
  etaH: number;
  support: number;
  channel: string;
}

export interface SceneIndex {
  scene: Scene;
  count: number;

  id: string[];
  name: string[];
  systemCode: string[];
  group: string[];
  type: string[];
  gmina: string[];
  voiv: string[];
  lat: Float64Array;
  lon: Float64Array;
  critClass: string[];
  critScore: Float64Array;
  population: Float64Array;
  backupType: string[];
  autonomyH: Float64Array;
  fuelH: Float64Array;
  restoreH: Float64Array;
  operator: string[];
  onRegister: Uint8Array;
  spo10: Uint8Array;
  inFloodZone: Uint8Array;
  planStatus: string[];
  hasContact: Uint8Array;
  hasAgreement: Uint8Array;
  responsiveness: Float64Array;
  lastContactTest: string[];
  lastExercise: string[];

  /** Lista sąsiedztwa w formacie CSR: krawędzie węzła `n` to `[edgeStart[n], edgeStart[n+1])`. */
  edgeStart: Int32Array;
  edgeTarget: Int32Array;
  edgeImpact: Float64Array;
  edgeLag: Float64Array;
  edgeDependency: string[];
  edgeRedundancy: string[];

  gminaPopulation: Record<string, number>;
  gminaNames: Record<string, string>;
  systemByCode: Map<string, SystemInfo>;
  voivName: Map<string, string>;
  byId: Map<string, number>;
  reports: OperatorReport[];
}

export function indexScene(scene: Scene): SceneIndex {
  const n = scene.nodes.length;
  const col = (i: number) => scene.nodes.map((r) => r[i]);

  const f = (i: number): Float64Array => {
    const a = new Float64Array(n);
    for (let k = 0; k < n; k += 1) a[k] = Number(scene.nodes[k][i]) || 0;
    return a;
  };
  const u = (i: number): Uint8Array => {
    const a = new Uint8Array(n);
    for (let k = 0; k < n; k += 1) a[k] = Number(scene.nodes[k][i]) ? 1 : 0;
    return a;
  };

  const id = col(0) as string[];
  const byId = new Map<string, number>();
  id.forEach((v, i) => byId.set(v, i));

  // CSR: najpierw zliczamy krawędzie wychodzące, potem wypełniamy tablice.
  // Dzięki temu symulacja iteruje po ciągłym fragmencie pamięci zamiast po
  // tablicy tablic, co przy 6552 krawędziach i przeliczaniu na każdy ruch
  // suwaka robi zauważalną różnicę.
  const m = scene.edges.length;
  const degree = new Int32Array(n + 1);
  for (const e of scene.edges) degree[Number(e[0]) + 1] += 1;
  for (let i = 0; i < n; i += 1) degree[i + 1] += degree[i];
  const edgeStart = degree;
  const cursor = Int32Array.from(edgeStart);

  const edgeTarget = new Int32Array(m);
  const edgeImpact = new Float64Array(m);
  const edgeLag = new Float64Array(m);
  const edgeDependency = new Array<string>(m);
  const edgeRedundancy = new Array<string>(m);

  for (const e of scene.edges) {
    const s = Number(e[0]);
    const at = cursor[s];
    cursor[s] += 1;
    edgeTarget[at] = Number(e[1]);
    edgeDependency[at] = String(e[2]);
    edgeImpact[at] = Number(e[3]);
    edgeLag[at] = Number(e[4]);
    edgeRedundancy[at] = String(e[5]);
  }

  return {
    scene,
    count: n,
    id,
    name: col(1) as string[],
    systemCode: col(2) as string[],
    group: col(3) as string[],
    type: col(4) as string[],
    gmina: col(5) as string[],
    voiv: col(6) as string[],
    lat: f(7),
    lon: f(8),
    critClass: col(9) as string[],
    critScore: f(10),
    population: f(11),
    backupType: col(12) as string[],
    autonomyH: f(13),
    fuelH: f(14),
    restoreH: f(15),
    operator: col(16) as string[],
    onRegister: u(17),
    spo10: u(18),
    inFloodZone: u(19),
    planStatus: col(20) as string[],
    hasContact: u(21),
    hasAgreement: u(22),
    responsiveness: f(23),
    lastContactTest: col(24) as string[],
    lastExercise: col(25) as string[],
    edgeStart,
    edgeTarget,
    edgeImpact,
    edgeLag,
    edgeDependency,
    edgeRedundancy,
    gminaPopulation: scene.gminaPopulation,
    gminaNames: scene.gminaNames,
    systemByCode: new Map(scene.systems.map((s) => [s.code, s])),
    voivName: new Map(scene.voivodeships.map((v) => [v.code, v.name])),
    byId,
    reports: scene.reports.map((r) => ({
      time: String(r[0]),
      node: Number(r[1]),
      kind: String(r[2]),
      severity: String(r[3]),
      etaH: Number(r[4]),
      support: Number(r[5]),
      channel: String(r[6]),
    })),
  };
}

/* ------------------------------------------------------------------ */
/* Zegar sceny                                                         */
/* ------------------------------------------------------------------ */

/**
 * Ile minut zegara ściennego przypada na jedną godzinę scenariusza.
 * 0,5 min × 97 klatek ≈ 48 minut na pełny przebieg powodzi.
 */
export const MINUTES_PER_FRAME = 0.5;

/**
 * Klatka odpowiadająca bieżącej chwili zegara.
 *
 * Punkt zaczepienia liczony jest od epoki, nie od uruchomienia aplikacji, więc
 * demonstracja wygląda tak samo o każdej porze, odświeżenie strony nie cofa
 * przebiegu, a dwie osoby patrzące jednocześnie widzą tę samą godzinę.
 */
export function liveFrameIndex(frameCount: number, now: number = Date.now()): number {
  if (frameCount <= 0) return 0;
  const frameMs = MINUTES_PER_FRAME * 60_000;
  const cycleMs = frameCount * frameMs;
  const phase = ((now % cycleMs) + cycleMs) % cycleMs;
  // Dzielimy przez długość klatki, nie przez długość cyklu przemnożoną przez
  // ich liczbę: ta druga postać przy niektórych chwilach schodzi o ułamek
  // poniżej całkowitej i część klatek pokazuje dwa razy, a część wcale.
  return Math.min(frameCount - 1, Math.floor(phase / frameMs));
}

/** Ile milisekund pozostało do przeskoku na następną klatkę. */
export function msToNextFrame(frameCount: number, now: number = Date.now()): number {
  if (frameCount <= 0) return 60_000;
  const frameMs = MINUTES_PER_FRAME * 60_000;
  const cycleMs = frameCount * frameMs;
  const phase = ((now % cycleMs) + cycleMs) % cycleMs;
  return frameMs - (phase % frameMs);
}

/* ------------------------------------------------------------------ */
/* Rzut kartograficzny                                                 */
/* ------------------------------------------------------------------ */

/**
 * Musi być identyczne z BOUNDS w `components/CountryMap.tsx` oraz w generatorze
 * `tools/build_poland_geo.py`. Rozjazd tych trzech miejsc przesunie punkty
 * względem granic województw.
 */
export const BOUNDS = { minLat: 49.0, maxLat: 54.9, minLon: 14.1, maxLon: 24.2 };

export function project(lat: number, lon: number, w = 100, h = 100): { x: number; y: number } {
  return {
    x: ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * w,
    y: h - ((lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) * h,
  };
}

/* ------------------------------------------------------------------ */
/* Skale i formatowanie                                                */
/* ------------------------------------------------------------------ */

/**
 * Skala powagi wspólna dla całego programu demo.
 * Cztery rozróżnialne stopnie — żadne dwa nie mogą mieć tej samej barwy.
 */
export const SEVERITY_LEVELS = [
  { max: 25, label: 'niski', color: '#15803d' },
  { max: 50, label: 'podwyższony', color: '#a16207' },
  { max: 75, label: 'wysoki', color: '#c2410c' },
  { max: Infinity, label: 'krytyczny', color: '#d5233f' },
] as const;

export function severityColor(value: number): string {
  for (const level of SEVERITY_LEVELS) {
    if (value < level.max) return level.color;
  }
  return SEVERITY_LEVELS[SEVERITY_LEVELS.length - 1].color;
}

export function severityLabel(value: number): string {
  for (const level of SEVERITY_LEVELS) {
    if (value < level.max) return level.label;
  }
  return SEVERITY_LEVELS[SEVERITY_LEVELS.length - 1].label;
}

/** Barwy grup systemów — jakościowe, nie porządkowe, więc bez skali powagi. */
export const GROUP_COLORS: Record<string, string> = {
  energy: '#b45309',
  water: '#0369a1',
  health: '#be123c',
  telecom: '#6d28d9',
  ict: '#4338ca',
  transport: '#0f766e',
  food: '#4d7c0f',
  admin: '#0052a5',
  finance: '#7e22ce',
  rescue: '#c2410c',
  chemical: '#a16207',
};

export const GROUP_LABELS: Record<string, string> = {
  energy: 'energetyka',
  water: 'woda',
  health: 'zdrowie',
  telecom: 'telekomunikacja',
  ict: 'teleinformatyka',
  transport: 'transport',
  food: 'żywność',
  admin: 'administracja',
  finance: 'finanse',
  rescue: 'ratownictwo',
  chemical: 'chemia',
};

export function groupColor(group: string): string {
  return GROUP_COLORS[group] ?? '#64748b';
}

export function groupLabel(group: string): string {
  return GROUP_LABELS[group] ?? group;
}

export function formatNumber(value: number, digits = 0): string {
  return value.toLocaleString('pl-PL', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatHours(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 48) return `${formatNumber(hours, 1)} h`;
  return `${formatNumber(hours / 24, 1)} d`;
}

/** Skraca wygenerowaną nazwę obiektu do postaci czytelnej w tabeli. */
export function shortNodeName(name: string): string {
  return name.replace(/\s+[a-ząćęłńóśźż]+-[a-ząćęłńóśźż]+-\d+-\d+(-\d+)?$/i, '').trim() || name;
}

/** Skraca wygenerowaną nazwę gminy. */
export function shortGminaName(name: string): string {
  return name.replace(/^gmina\s+/i, '').replace(/-/g, ' ');
}

/** Chwila scenariusza dla danej klatki powodzi. */
export function frameTime(meta: SceneMeta, frame: number): Date {
  const start = new Date(meta.floodStart).getTime();
  return new Date(start + frame * meta.frameHours * 3_600_000);
}
