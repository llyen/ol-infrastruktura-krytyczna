/**
 * Testy modelu „Symulatora kaskad IK".
 *
 * Najważniejsze są kotwice regresyjne: symulacja w przeglądarce musi dawać te
 * same liczby, co `cascade_engine.py`. Bez tego aplikacja i raporty pokazywałyby
 * różne skutki tej samej awarii, a to podważa całą demonstrację.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_HORIZON_H,
  FULL_REDUNDANCY_FACTOR,
  PARTIAL_REDUNDANCY_FACTOR,
  effectTree,
  firstHours,
  simulate,
} from '@/data/cascade';
import {
  MINUTES_PER_FRAME,
  SEVERITY_LEVELS,
  formatHours,
  frameTime,
  groupColor,
  indexScene,
  liveFrameIndex,
  msToNextFrame,
  severityColor,
  shortNodeName,
  type Scene,
} from '@/data/model';
import {
  canActOn,
  canSeeDependencyGraph,
  canWrite,
  cooperationGaps,
  dedupeReports,
  fuelPriority,
  suggestedLitres,
  validateFuelRequest,
  validateHardeningDecision,
  validateOperatorReport,
  validateScenario,
  type Actor,
} from '@/services/workflow';

const scene = JSON.parse(
  readFileSync(resolve(__dirname, '../../public/data/scene.json'), 'utf-8'),
) as Scene;
const index = indexScene(scene);

const rcb: Actor = {
  id: 'u1',
  name: 'Dyżurny RCB',
  role: 'RCB',
  voivodeshipCode: '',
  operatorName: '',
};

describe('scena', () => {
  it('ma tyle węzłów i krawędzi, ile zapowiada metryka', () => {
    expect(index.count).toBe(scene.meta.nodeCount);
    expect(index.edgeTarget.length).toBe(scene.meta.edgeCount);
  });

  it('indeks CSR pokrywa wszystkie krawędzie bez luk', () => {
    expect(index.edgeStart[0]).toBe(0);
    expect(index.edgeStart[index.count]).toBe(scene.meta.edgeCount);
    for (let i = 0; i < index.count; i += 1) {
      expect(index.edgeStart[i + 1]).toBeGreaterThanOrEqual(index.edgeStart[i]);
    }
  });
});

describe('kotwice symulacji — zgodność z cascade_engine.py', () => {
  const headline = scene.meta.headline;
  const seed = index.byId.get(headline.trigger_node_id);

  it('obiekt inicjujący z metryki jest w scenie', () => {
    expect(seed).toBeDefined();
  });

  it('pojedyncza awaria daje ten sam zasięg, co silnik referencyjny', () => {
    const result = simulate(index, {
      seeds: new Map([[seed as number, 0]]),
      horizonHours: DEFAULT_HORIZON_H,
    });
    expect(result.nodesSecondary).toBe(headline.secondary_nodes);
    expect(result.nodesFailed).toBe(headline.secondary_nodes + 1);
    expect(result.maxWave).toBe(headline.max_wave);
    expect(result.affectedPopulation).toBe(headline.people_without_power);
    expect(result.firstSecondaryHour).toBeCloseTo(headline.first_secondary_hour, 2);
  });

  it('najgorszy pojedynczy obiekt krajowo zgadza się co do liczby ofiar usług', () => {
    const worst = scene.meta.worstSingleNode;
    const node = index.byId.get(worst.node_id);
    expect(node).toBeDefined();
    const result = simulate(index, {
      seeds: new Map([[node as number, 0]]),
      horizonHours: DEFAULT_HORIZON_H,
    });
    expect(result.nodesFailed).toBe(worst.nodes_failed_total);
    expect(result.affectedPopulation).toBe(worst.affected_population);
  });

  it('krótszy horyzont nie może dać większego zasięgu niż dłuższy', () => {
    const short = simulate(index, { seeds: new Map([[seed as number, 0]]), horizonHours: 12 });
    const long = simulate(index, { seeds: new Map([[seed as number, 0]]), horizonHours: 240 });
    expect(short.nodesFailed).toBeLessThanOrEqual(long.nodesFailed);
  });
});

describe('reguły propagacji', () => {
  const seed = index.byId.get(scene.meta.headline.trigger_node_id) as number;

  it('redundancja tłumi wpływ zgodnie ze współczynnikami z silnika', () => {
    expect(FULL_REDUNDANCY_FACTOR).toBeCloseTo(0.4, 5);
    expect(PARTIAL_REDUNDANCY_FACTOR).toBeCloseTo(0.9, 5);
    expect(FULL_REDUNDANCY_FACTOR).toBeLessThan(PARTIAL_REDUNDANCY_FACTOR);
  });

  it('podniesienie autonomii nie może pogorszyć wyniku', () => {
    const base = simulate(index, { seeds: new Map([[seed, 0]]) });
    const bonus = new Map<number, number>();
    for (const e of base.events) if (e.wave > 0) bonus.set(e.node, 24);
    const better = simulate(index, { seeds: new Map([[seed, 0]]), autonomyBonus: bonus });
    expect(better.nodesFailed).toBeLessThanOrEqual(base.nodesFailed);
    expect(better.affectedPopulation).toBeLessThanOrEqual(base.affectedPopulation);
  });

  it('założenie sprawnych agregatów nie zwiększa liczby awarii', () => {
    const strict = simulate(index, { seeds: new Map([[seed, 0]]) });
    const lenient = simulate(index, {
      seeds: new Map([[seed, 0]]),
      assumeAllBackupsWork: true,
    });
    expect(lenient.nodesFailed).toBeLessThanOrEqual(strict.nodesFailed);
  });

  it('zdarzenia są uporządkowane w czasie i każdy węzeł pada najwyżej raz', () => {
    const result = simulate(index, { seeds: new Map([[seed, 0]]) });
    const seen = new Set<number>();
    let previous = -1;
    for (const e of result.events) {
      expect(seen.has(e.node)).toBe(false);
      seen.add(e.node);
      expect(e.failHour).toBeGreaterThanOrEqual(previous);
      previous = e.failHour;
    }
  });

  it('symulacja jest powtarzalna — dwa przebiegi dają identyczną listę', () => {
    const a = simulate(index, { seeds: new Map([[seed, 0]]) });
    const b = simulate(index, { seeds: new Map([[seed, 0]]) });
    expect(a.events.map((e) => e.node)).toEqual(b.events.map((e) => e.node));
  });

  it('ludność liczona jest po gminach, więc nie przekracza ludności kraju', () => {
    const total = Object.values(index.gminaPopulation).reduce((s, v) => s + v, 0);
    const result = simulate(index, { seeds: new Map([[seed, 0]]) });
    expect(result.affectedPopulation).toBeLessThanOrEqual(total);
  });

  it('drzewo skutków obejmuje wszystkie zdarzenia', () => {
    const result = simulate(index, { seeds: new Map([[seed, 0]]) });
    const tree = effectTree(result);
    let counted = 0;
    for (const children of tree.values()) counted += children.length;
    expect(counted).toBe(result.events.length);
  });

  it('pierwsze godziny to podzbiór pełnego przebiegu', () => {
    const result = simulate(index, { seeds: new Map([[seed, 0]]) });
    const shock = firstHours(result, 6);
    expect(shock.length).toBeLessThanOrEqual(result.events.length);
    for (const e of shock) expect(e.failHour).toBeLessThanOrEqual(6);
  });
});

describe('scenariusz powodziowy odtwarzany z klatek', () => {
  const flood = scene.meta.floodScenario;

  it('suma klatek to pełna lista obiektów, które padły', () => {
    const total = scene.floodFrames.reduce((s, f) => s + f.length, 0);
    expect(total).toBe(flood.nodes_failed_total);
  });

  it('klatki są rozłączne — żaden obiekt nie pada dwa razy', () => {
    const seen = new Set<number>();
    for (const f of scene.floodFrames) {
      for (const [node] of f) {
        expect(seen.has(node)).toBe(false);
        seen.add(node);
      }
    }
  });

  it('liczba skutków wtórnych w klatkach zgadza się z metryką', () => {
    let secondary = 0;
    for (const f of scene.floodFrames) for (const [, wave] of f) if (wave > 0) secondary += 1;
    expect(secondary).toBe(flood.nodes_failed_secondary);
  });

  it('powódź uderza mocniej niż pojedyncza awaria — wzmocnienie ma sens', () => {
    expect(flood.affected_population).toBeGreaterThan(scene.meta.headline.people_without_power);
    expect(flood.amplification_ratio).toBeGreaterThan(1);
  });
});

describe('zegar sceny', () => {
  const count = scene.floodFrames.length;

  it('odwiedza każdą klatkę dokładnie raz w pełnym cyklu', () => {
    const seen = new Set<number>();
    const frameMs = MINUTES_PER_FRAME * 60_000;
    for (let j = 0; j < count; j += 1) seen.add(liveFrameIndex(count, j * frameMs));
    expect(seen.size).toBe(count);
  });

  it('nie zależy od pory uruchomienia — ta sama chwila daje tę samą klatkę', () => {
    const now = Date.UTC(2025, 4, 17, 3, 41, 7);
    expect(liveFrameIndex(count, now)).toBe(liveFrameIndex(count, now));
    const cycle = count * MINUTES_PER_FRAME * 60_000;
    expect(liveFrameIndex(count, now)).toBe(liveFrameIndex(count, now + cycle));
  });

  it('czas do następnej klatki mieści się w długości klatki', () => {
    const frameMs = MINUTES_PER_FRAME * 60_000;
    for (let j = 0; j < 50; j += 1) {
      const ms = msToNextFrame(count, j * 7919);
      expect(ms).toBeGreaterThan(0);
      expect(ms).toBeLessThanOrEqual(frameMs);
    }
  });

  it('chwila scenariusza rośnie wraz z numerem klatki', () => {
    const a = frameTime(scene.meta, 0).getTime();
    const b = frameTime(scene.meta, 10).getTime();
    expect(b - a).toBeCloseTo(10 * scene.meta.frameHours * 3_600_000, 0);
  });
});

describe('skale', () => {
  it('każdy stopień powagi ma inną barwę', () => {
    const colors = new Set(SEVERITY_LEVELS.map((l) => l.color));
    expect(colors.size).toBe(SEVERITY_LEVELS.length);
  });

  it('skala powagi jest monotoniczna — sąsiednie stopnie się nie mieszają', () => {
    expect(severityColor(10)).toBe(SEVERITY_LEVELS[0].color);
    expect(severityColor(40)).toBe(SEVERITY_LEVELS[1].color);
    expect(severityColor(60)).toBe(SEVERITY_LEVELS[2].color);
    expect(severityColor(95)).toBe(SEVERITY_LEVELS[3].color);
  });

  it('grupy systemów mają rozróżnialne barwy', () => {
    const groups = [...new Set(index.group)];
    const colors = new Set(groups.map(groupColor));
    expect(colors.size).toBe(groups.length);
  });

  it('formatowanie czasu przechodzi z minut na godziny i doby', () => {
    expect(formatHours(0.5)).toContain('min');
    expect(formatHours(12)).toContain('h');
    expect(formatHours(72)).toContain('d');
  });

  it('skracanie nazwy usuwa wygenerowany sufiks, ale nie kasuje nazwy', () => {
    for (let i = 0; i < 200; i += 1) {
      expect(shortNodeName(index.name[i]).length).toBeGreaterThan(0);
    }
  });
});

describe('uprawnienia', () => {
  it('operator IK nie widzi pełnego grafu zależności', () => {
    expect(canSeeDependencyGraph('operator IK')).toBe(false);
    expect(canSeeDependencyGraph('RCB')).toBe(true);
  });

  it('audytor ma wyłącznie odczyt', () => {
    expect(canWrite('audytor')).toBe(false);
    expect(canWrite('decydent')).toBe(true);
  });

  it('operator działa tylko na własnych obiektach', () => {
    const operator: Actor = { ...rcb, role: 'operator IK', operatorName: 'Alfa' };
    expect(canActOn(operator, { voiv: '14', operator: 'Alfa' })).toBe(true);
    expect(canActOn(operator, { voiv: '14', operator: 'Beta' })).toBe(false);
  });

  it('wojewoda działa tylko w swoim województwie', () => {
    const wojewoda: Actor = { ...rcb, role: 'wojewoda / WCZK', voivodeshipCode: '02' };
    expect(canActOn(wojewoda, { voiv: '02', operator: 'Alfa' })).toBe(true);
    expect(canActOn(wojewoda, { voiv: '14', operator: 'Alfa' })).toBe(false);
  });
});

describe('walidacje formularzy', () => {
  it('scenariusz wymaga nazwy, obiektu i horyzontu w zakresie', () => {
    const base = {
      scene_time: '2025-05-17T00:00:00Z',
      seed_node_id: '',
      seed_node_name: '',
      voivodeship_code: '02',
      mode: 'awaria natychmiastowa',
      horizon_hours: 400,
      assume_backups: false,
      nodes_failed: 1,
      nodes_secondary: 0,
      max_wave: 0,
      affected_gminas: 1,
      affected_population: 1,
      k1_nodes_failed: 0,
      first_secondary_hour: 0,
      title: 'ok',
      note: '',
    };
    const bad = validateScenario(base, rcb);
    expect(bad.ok).toBe(false);
    expect(bad.errors.length).toBe(3);

    const good = validateScenario(
      { ...base, seed_node_id: 'IK-01-00001', horizon_hours: 48, title: 'Ćwiczenie wojewódzkie' },
      rcb,
    );
    expect(good.ok).toBe(true);
  });

  it('audytor nie zapisze scenariusza', () => {
    const audytor: Actor = { ...rcb, role: 'audytor' };
    const v = validateScenario(
      {
        scene_time: '2025-05-17T00:00:00Z',
        seed_node_id: 'IK-01-00001',
        seed_node_name: 'x',
        voivodeship_code: '02',
        mode: 'awaria natychmiastowa',
        horizon_hours: 48,
        assume_backups: false,
        nodes_failed: 1,
        nodes_secondary: 0,
        max_wave: 0,
        affected_gminas: 1,
        affected_population: 1,
        k1_nodes_failed: 0,
        first_secondary_hour: 0,
        title: 'Ćwiczenie kontrolne',
        note: '',
      },
      audytor,
    );
    expect(v.ok).toBe(false);
  });

  it('zapotrzebowanie na paliwo wymaga uzasadnienia i zgodnego województwa', () => {
    const wojewoda: Actor = { ...rcb, role: 'wojewoda / WCZK', voivodeshipCode: '02' };
    const draft = {
      scene_time: '2025-05-17T00:00:00Z',
      node_id: 'IK-01-00001',
      node_name: 'x',
      voivodeship_code: '14',
      gmina_code: '1',
      operator_name: 'Alfa',
      hours_remaining: 3,
      litres_requested: 500,
      priority: 'pilny',
      justification: 'za krótko',
      status: 'zgłoszone',
    };
    const bad = validateFuelRequest(draft, wojewoda);
    expect(bad.ok).toBe(false);
    expect(bad.errors.length).toBe(2);

    const good = validateFuelRequest(
      {
        ...draft,
        voivodeship_code: '02',
        justification: 'Szpital powiatowy na agregacie, zapas paliwa poniżej sześciu godzin.',
      },
      wojewoda,
    );
    expect(good.ok).toBe(true);
  });

  it('meldunek o niedziałającym obiekcie wymaga rezerwy i czasu przywrócenia', () => {
    const operator: Actor = { ...rcb, role: 'operator IK', operatorName: 'Alfa' };
    const draft = {
      scene_time: '2025-05-17T00:00:00Z',
      node_id: 'IK-01-00001',
      node_name: 'x',
      operator_name: 'Alfa',
      voivodeship_code: '02',
      event_kind: 'zalanie obiektu',
      node_state: 'down',
      has_backup: true,
      fuel_hours: 0,
      eta_restore_hours: 0,
      support_requested: '',
      description: '',
      offline_sync_id: '',
      capture_mode: 'online',
    };
    const bad = validateOperatorReport(draft, operator);
    expect(bad.ok).toBe(false);
    expect(bad.errors.length).toBe(2);

    const good = validateOperatorReport(
      { ...draft, fuel_hours: 8, eta_restore_hours: 12 },
      operator,
    );
    expect(good.ok).toBe(true);
  });

  it('operator nie zamelduje o cudzym obiekcie', () => {
    const operator: Actor = { ...rcb, role: 'operator IK', operatorName: 'Alfa' };
    const v = validateOperatorReport(
      {
        scene_time: '2025-05-17T00:00:00Z',
        node_id: 'IK-01-00001',
        node_name: 'x',
        operator_name: 'Beta',
        voivodeship_code: '02',
        event_kind: 'awaria techniczna',
        node_state: 'degraded',
        has_backup: false,
        fuel_hours: 0,
        eta_restore_hours: 0,
        support_requested: '',
        description: '',
        offline_sync_id: '',
        capture_mode: 'online',
      },
      operator,
    );
    expect(v.ok).toBe(false);
  });

  it('plan wzmocnień wymaga niepustego koszyka i uzasadnienia', () => {
    const decydent: Actor = { ...rcb, role: 'decydent' };
    const draft = {
      scene_time: '2025-05-17T00:00:00Z',
      variant: 'WŁASNY',
      node_ids: '',
      node_count: 0,
      nodes_saved: 0,
      population_saved: 0,
      decision: 'zatwierdzony',
      justification: 'krótko',
      supersedes: '',
    };
    expect(validateHardeningDecision(draft, decydent).errors.length).toBe(2);
    expect(
      validateHardeningDecision(
        {
          ...draft,
          node_count: 3,
          justification: 'Trzy obiekty ratują największą liczbę mieszkańców na złotówkę.',
        },
        decydent,
      ).ok,
    ).toBe(true);
  });
});

describe('tryb terenowy', () => {
  it('powtórzona wysyłka nie tworzy drugiego meldunku', () => {
    const rows = [
      { offline_sync_id: 'a', created_at: new Date('2025-05-17T10:00:00Z'), v: 1 },
      { offline_sync_id: 'a', created_at: new Date('2025-05-17T10:05:00Z'), v: 2 },
      { offline_sync_id: '', created_at: new Date('2025-05-17T10:01:00Z'), v: 3 },
      { offline_sync_id: '', created_at: new Date('2025-05-17T10:02:00Z'), v: 4 },
    ];
    const out = dedupeReports(rows);
    expect(out.length).toBe(3);
    expect(out.find((r) => r.offline_sync_id === 'a')?.v).toBe(2);
  });
});

describe('podpowiedzi operacyjne', () => {
  it('paliwo dowozi się do celu, a nie ponad niego', () => {
    expect(suggestedLitres(48, 48)).toBe(0);
    expect(suggestedLitres(60, 48)).toBe(0);
    expect(suggestedLitres(6, 48)).toBeGreaterThan(0);
    expect(suggestedLitres(6, 48) % 50).toBe(0);
  });

  it('priorytet rośnie przy niskim zapasie i klasie K1', () => {
    expect(fuelPriority(3, 'K3')).toBe('pilny');
    expect(fuelPriority(30, 'K1')).toBe('pilny');
    expect(fuelPriority(9, 'K3')).toBe('podwyższony');
    expect(fuelPriority(30, 'K3')).toBe('zwykły');
  });

  it('braki we współpracy są wypisane słowami, nie flagami', () => {
    const gaps = cooperationGaps({
      planStatus: 'w opracowaniu',
      hasContact: 0,
      hasAgreement: 0,
      onRegister: 0,
      lastContactTest: '',
    });
    expect(gaps.length).toBe(5);
    expect(gaps.every((g) => g.length > 5)).toBe(true);

    const clean = cooperationGaps({
      planStatus: 'zatwierdzony',
      hasContact: 1,
      hasAgreement: 1,
      onRegister: 1,
      lastContactTest: new Date().toISOString().slice(0, 10),
    });
    expect(clean.length).toBe(0);
  });
});
