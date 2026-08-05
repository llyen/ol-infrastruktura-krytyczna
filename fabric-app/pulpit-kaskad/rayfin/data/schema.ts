import { ExerciseScenario } from './ExerciseScenario.js';
import { FuelRequest } from './FuelRequest.js';
import { OperatorReport } from './OperatorReport.js';
import { CooperationAction } from './CooperationAction.js';
import { HardeningDecision } from './HardeningDecision.js';

export type AppSchema = {
  ExerciseScenario: ExerciseScenario;
  FuelRequest: FuelRequest;
  OperatorReport: OperatorReport;
  CooperationAction: CooperationAction;
  HardeningDecision: HardeningDecision;
};

export const schema = [
  ExerciseScenario,
  FuelRequest,
  OperatorReport,
  CooperationAction,
  HardeningDecision,
];
