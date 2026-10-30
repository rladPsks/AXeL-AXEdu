import type { ComponentType } from "react";
// A adds feature modules here; shared shell, API and session remain owned by B.
export type CaseFeature = {
  id: string;
  title: string;
  Component: ComponentType<{ caseId: string }>;
};
export const additionalCaseFeatures: CaseFeature[] = [];
