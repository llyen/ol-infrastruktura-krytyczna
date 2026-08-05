import { entity, role, text, int, decimal, date, uuid } from '@microsoft/rayfin-core';

/**
 * Zapotrzebowanie na paliwo do agregatu (Ekran 2 - Obraz biezacy).
 *
 * Status zmienia sie przez kolejny wpis, a nie przez nadpisanie: gdy obiekt
 * padnie mimo zlozonego wniosku, musi dac sie odtworzyc, kiedy wniosek zlozono
 * i ile godzin zapasu wtedy zostawalo.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class FuelRequest {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) request_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ min: 3, max: 30 }) node_id!: string;
  @text({ max: 200 }) node_name!: string;
  @text({ max: 4 }) voivodeship_code!: string;
  @text({ max: 12 }) gmina_code!: string;
  @text({ max: 160 }) operator_name!: string;
  /** Zapas paliwa w chwili zlozenia wniosku - kontekst decyzji. */
  @decimal() hours_remaining!: number;
  @int() litres_requested!: number;
  /** 'pilny' | 'podwyzszony' | 'zwykly'. */
  @text({ min: 3, max: 20 }) priority!: string;
  @text({ min: 30, max: 1000 }) justification!: string;
  /** 'zlozony' | 'obsluzony' | 'przekazany do CZK'. */
  @text({ min: 3, max: 40 }) status!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
