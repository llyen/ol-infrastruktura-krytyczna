import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { REGIONS } from '@/data/poland';
import { BOUNDS, indexScene, type Scene } from '@/data/model';

/**
 * Wspolrzedne w scenie musza lezec wewnatrz granic rysowanych na mapie.
 *
 * Zbiory zrodlowe rozrzucaja obiekty losowym odchyleniem wokol srodka
 * wojewodztwa, wiec czesc z nich wypadala poza wlasnym regionem, a kilkadziesiat
 * nawet poza granica kraju. `tools/build_scene.py` przyciaga takie punkty do
 * wlasnego wojewodztwa. Ten test pilnuje, zeby korekta nie zniknela przy
 * kolejnej przebudowie sceny - bez niej mapa myli sie co do tego, ktory region
 * jest dotkniety awaria.
 */

const scene = JSON.parse(
  readFileSync(resolve(__dirname, '../../public/data/scene.json'), 'utf-8'),
) as Scene;
const index = indexScene(scene);

function toXY(lat: number, lon: number): [number, number] {
  return [
    ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * 100,
    100 - ((lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) * 100,
  ];
}

/** Rozklada atrybut `d` na pierscienie punktow. Generator uzywa wylacznie M/L/Z. */
function ringsOf(path: string): [number, number][][] {
  return path
    .split('Z')
    .filter((chunk) => chunk.trim().length > 0)
    .map((chunk) =>
      [...chunk.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].map(
        (m) => [Number(m[1]), Number(m[2])] as [number, number],
      ),
    )
    .filter((ring) => ring.length > 3);
}

/** Nazwy wojewodztw w scenie sa bez znakow diakrytycznych, w granicach - z. */
function fold(text: string): string {
  return text
    .replace(/ł/g, 'l')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

const RINGS = new Map(REGIONS.map((r) => [fold(r.name), ringsOf(r.path)]));

/** Test parzystosci przeciec promienia poziomego. */
function inRings(x: number, y: number, rings: [number, number][][]): boolean {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0; i < ring.length; i += 1) {
      const [x1, y1] = ring[i];
      const [x2, y2] = ring[(i + 1) % ring.length];
      if (y1 > y !== y2 > y && x < x1 + ((y - y1) * (x2 - x1)) / (y2 - y1)) {
        inside = !inside;
      }
    }
  }
  return inside;
}

const regionByCode = new Map(
  scene.voivodeships.map((v) => [v.code, RINGS.get(fold(v.name))] as const),
);

describe('granice wojewodztw', () => {
  it('plik granic zawiera 16 wojewodztw z niepustym konturem', () => {
    expect(REGIONS).toHaveLength(16);
    for (const region of REGIONS) {
      expect(ringsOf(region.path).length).toBeGreaterThan(0);
    }
  });

  it('kazde wojewodztwo ze sceny ma odpowiednik w granicach', () => {
    for (const [, rings] of regionByCode) {
      expect(rings).toBeDefined();
    }
  });
});

describe('polozenie obiektow infrastruktury', () => {
  it('kazdy obiekt lezy w swoim wojewodztwie', () => {
    const wrong: string[] = [];
    for (let i = 0; i < index.count; i += 1) {
      const rings = regionByCode.get(index.voiv[i]);
      if (!rings) continue;
      const [x, y] = toXY(index.lat[i], index.lon[i]);
      if (!inRings(x, y, rings)) wrong.push(index.id[i]);
    }
    expect(wrong).toEqual([]);
  });

  it('zaden obiekt nie wypada poza ramke mapy', () => {
    for (let i = 0; i < index.count; i += 1) {
      expect(index.lat[i]).toBeGreaterThanOrEqual(BOUNDS.minLat);
      expect(index.lat[i]).toBeLessThanOrEqual(BOUNDS.maxLat);
      expect(index.lon[i]).toBeGreaterThanOrEqual(BOUNDS.minLon);
      expect(index.lon[i]).toBeLessThanOrEqual(BOUNDS.maxLon);
    }
  });
});
