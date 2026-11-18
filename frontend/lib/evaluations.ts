export const EVALUATION_KIND_LABELS = {
  prueba: "Prueba",
  control: "Control",
  tarea: "Tarea",
  proyecto: "Proyecto",
  examen: "Examen",
  otro: "Otro",
} as const;

export type EvaluationKind = keyof typeof EVALUATION_KIND_LABELS;

export const EVALUATION_KINDS = Object.keys(EVALUATION_KIND_LABELS) as EvaluationKind[];
