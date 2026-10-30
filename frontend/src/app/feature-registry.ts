import type { ComponentType } from "react";
import { IntakeDetail } from "../features/intake";
// A adds feature modules here; shared shell, API and session remain owned by B.
export type CaseFeature = {
  id: string;
  title: string;
  Component: ComponentType<{ caseId: string }>;
};
export const additionalCaseFeatures: CaseFeature[] = [
  { id: "intake", title: "접수·AI 분류", Component: IntakeDetail },
];
