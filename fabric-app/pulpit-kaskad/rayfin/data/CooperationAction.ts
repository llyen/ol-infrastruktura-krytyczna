import { entity, role, text, date, uuid } from '@microsoft/rayfin-core';

/**
 * Dzialanie ze wspolpracy SPO-10 (Ekran 4): test kontaktu, wniosek o wpis
 * do rejestru IK, zaplanowanie cwiczenia, wezwanie do aktualizacji planu.
 *
 * `gap_reason` przechowuje luke, ktora wywolala dzialanie. Bez niej rejestr
 * mowi, ze cos zrobiono, ale nie mowi dlaczego - a to wlasnie jest tresc
 * przy rozliczaniu wspolpracy z operatorem.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class CooperationAction {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) action_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ min: 3, max: 30 }) node_id!: string;
  @text({ max: 200 }) node_name!: string;
  @text({ max: 160 }) operator_name!: string;
  @text({ max: 4 }) voivodeship_code!: string;
  @text({ min: 3, max: 60 }) action_kind!: string;
  @text({ max: 400 }) gap_reason!: string;
  @text({ max: 20 }) due_date!: string;
  @text({ max: 1000 }) note!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
