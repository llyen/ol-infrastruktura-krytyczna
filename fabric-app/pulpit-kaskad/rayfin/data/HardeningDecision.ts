import { entity, role, text, int, date, uuid } from '@microsoft/rayfin-core';

/**
 * Decyzja o wzmocnieniu infrastruktury (Ekran 5) - jednoczesnie slad audytowy.
 *
 * Gdy zdarzenie wystapi, z tego rejestru wynika, kto wiedzial o slabym punkcie,
 * kiedy sie o nim dowiedzial i co postanowil. Dlatego odrzucenie inwestycji
 * jest zapisywane tak samo starannie jak jej zatwierdzenie, a zmiana zdania
 * to nowy wpis wskazujacy poprzedni przez `supersedes`.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class HardeningDecision {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) decision_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ max: 40 }) variant!: string;
  /** Identyfikatory obiektow w koszyku, rozdzielone przecinkami. */
  @text({ max: 4000 }) node_ids!: string;
  @int() node_count!: number;
  @int() nodes_saved!: number;
  @int() population_saved!: number;
  /** 'zatwierdzony' | 'odrzucony' | 'odroczony'. */
  @text({ min: 3, max: 40 }) decision!: string;
  @text({ min: 30, max: 2000 }) justification!: string;
  @text({ max: 40 }) supersedes!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
