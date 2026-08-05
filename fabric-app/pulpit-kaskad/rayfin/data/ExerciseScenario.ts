import { entity, role, text, int, boolean, decimal, date, uuid } from '@microsoft/rayfin-core';

/**
 * Scenariusz cwiczebny zapisany z ekranu symulacji (Ekran 1).
 *
 * Zapisujemy zalozenia razem z wynikiem, bo bez nich liczba "538 453 osob bez
 * uslug" jest nieweryfikowalna - ta sama awaria przy innym horyzoncie i innym
 * zalozeniu o agregatach daje inny wynik. Brak akcji 'update': korekta to nowy
 * scenariusz, a nie podmiana wyniku pod ta sama nazwa.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class ExerciseScenario {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) scenario_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ min: 3, max: 30 }) seed_node_id!: string;
  @text({ max: 200 }) seed_node_name!: string;
  @text({ max: 4 }) voivodeship_code!: string;
  /** 'awaria natychmiastowa' | 'awaria zapowiedziana'. */
  @text({ min: 3, max: 40 }) mode!: string;
  @int() horizon_hours!: number;
  /** Zalozenie planistyczne "wszystkie agregaty sprawne". */
  @boolean() assume_backups!: boolean;
  @int() nodes_failed!: number;
  @int() nodes_secondary!: number;
  @int() max_wave!: number;
  @int() affected_gminas!: number;
  @int() affected_population!: number;
  @int() k1_nodes_failed!: number;
  @decimal() first_secondary_hour!: number;
  @text({ min: 5, max: 160 }) title!: string;
  @text({ max: 1000 }) note!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
