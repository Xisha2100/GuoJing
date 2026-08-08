import { describe, expect, it } from "vitest";

import { emptyDocument } from "../test/fixtures";
import { formatDocument, parseTutorialDocument } from "./document";

describe("tutorial document parsing", () => {
  it("round-trips a valid editor document", () => {
    expect(parseTutorialDocument(formatDocument(emptyDocument))).toEqual(
      emptyDocument,
    );
  });

  it("rejects JSON with the wrong schema version", () => {
    expect(() =>
      parseTutorialDocument(
        '{"schema_version":"2.0","graph":{},"captures":[]}',
      ),
    ).toThrow('schema_version 必须为 "1.0"');
  });

  it("rejects a missing captures array before making an API request", () => {
    expect(() =>
      parseTutorialDocument('{"schema_version":"1.0","graph":{}}'),
    ).toThrow("captures 数组");
  });
});
