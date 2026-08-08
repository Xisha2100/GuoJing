import type { TutorialDraftDocument } from "../api/types";

export function parseTutorialDocument(source: string): TutorialDraftDocument {
  const parsed: unknown = JSON.parse(source);
  if (!isRecord(parsed) || parsed.schema_version !== "1.0") {
    throw new Error('文档必须是对象，且 schema_version 必须为 "1.0"。');
  }
  if (!isRecord(parsed.graph)) {
    throw new Error("文档必须包含 graph 对象。");
  }
  if (!Array.isArray(parsed.captures)) {
    throw new Error("文档必须包含 captures 数组。");
  }
  return parsed as unknown as TutorialDraftDocument;
}

export function formatDocument(document: TutorialDraftDocument): string {
  return JSON.stringify(document, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
