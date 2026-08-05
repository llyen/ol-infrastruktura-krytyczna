import { entity, role, text, boolean, decimal, date, uuid } from '@microsoft/rayfin-core';

/**
 * Meldunek operatora IK (Ekran 3) - realizacja dwustronnej wymiany z SPO-10.
 *
 * `offline_sync_id` jest nadawany na urzadzeniu przed wysylka. Operator
 * z zalanego obiektu pracuje bez lacznosci i wysyla te sama paczke ponownie
 * po jej odzyskaniu; identyfikator pozwala rozpoznac powtorke zamiast tworzyc
 * drugi meldunek o tym samym zdarzeniu.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class OperatorReport {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) report_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ min: 3, max: 30 }) node_id!: string;
  @text({ max: 200 }) node_name!: string;
  @text({ max: 160 }) operator_name!: string;
  @text({ max: 4 }) voivodeship_code!: string;
  @text({ min: 3, max: 60 }) event_kind!: string;
  /** 'operational' | 'degraded' | 'down'. */
  @text({ min: 3, max: 20 }) node_state!: string;
  @boolean() has_backup!: boolean;
  @decimal() fuel_hours!: number;
  @decimal() eta_restore_hours!: number;
  /** Lista rozdzielona przecinkami: paliwo, pompy, transport, ochrona, lacznosc. */
  @text({ max: 200 }) support_requested!: string;
  @text({ max: 1000 }) description!: string;
  @text({ max: 60 }) offline_sync_id!: string;
  /** 'online' | 'offline'. */
  @text({ max: 20 }) capture_mode!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
