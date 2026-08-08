import { beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, workspace } from "../test/fixtures";
import { adminApi, ApiError } from "./client";

describe("adminApi", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("copies the CSRF cookie into mutation headers", async () => {
    document.cookie = "guojing_admin_csrf=csrf-value%2Bencoded; Path=/";
    fetchMock.mockResolvedValueOnce(jsonResponse(workspace(), 201));

    await adminApi.createWorkspace();

    expect(fetchMock).toHaveBeenCalledOnce();
    const [path, init] = fetchMock.mock.calls[0] ?? [];
    expect(path).toBe("/api/v1/admin/tutorial-drafts");
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe(
      "csrf-value+encoded",
    );
  });

  it("fails locally when a mutation has no CSRF cookie", async () => {
    await expect(adminApi.createWorkspace()).rejects.toMatchObject({
      status: 403,
    } satisfies Partial<ApiError>);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("preserves conflict details from the backend", async () => {
    document.cookie = "guojing_admin_csrf=csrf-value; Path=/";
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          detail: {
            message: "workspace changed",
            current_version: 3,
          },
        },
        409,
      ),
    );

    await expect(
      adminApi.replaceWorkspace("workspace-1", 1, workspace().document),
    ).rejects.toMatchObject({
      status: 409,
      message: "workspace changed",
      detail: { current_version: 3 },
    } satisfies Partial<ApiError>);
  });
});
