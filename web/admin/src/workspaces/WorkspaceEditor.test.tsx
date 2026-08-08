import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { jsonResponse, workspace } from "../test/fixtures";
import { WorkspaceEditor } from "./WorkspaceEditor";
import { formatDocument } from "./document";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "guojing_admin_csrf=csrf-value; Path=/";
});

it("saves with optimistic versioning, validates, and promotes", async () => {
  const user = userEvent.setup();
  const initial = workspace(1);
  const changedDocument = {
    ...initial.document,
    graph: { ...initial.document.graph, title: "微信添加好友" },
  };
  const saved = { ...workspace(2), document: changedDocument };
  const promoted = {
    workspace: { ...workspace(3), document: changedDocument },
    graph_id: "wechat-add-friend",
    revision_number: 1,
    created_at: "2026-08-08T10:30:00Z",
  };
  fetchMock
    .mockResolvedValueOnce(jsonResponse(saved))
    .mockResolvedValueOnce(
      jsonResponse({
        workspace_id: "workspace-1",
        version: 2,
        ready: true,
        issues: [],
      }),
    )
    .mockResolvedValueOnce(jsonResponse(promoted));
  render(
    <WorkspaceEditor
      initialWorkspace={initial}
      onBack={vi.fn()}
      onUnauthorized={vi.fn()}
    />,
  );

  fireEvent.change(screen.getByLabelText("教程工作区文档"), {
    target: { value: formatDocument(changedDocument) },
  });
  await user.click(screen.getByRole("button", { name: "保存" }));

  expect(await screen.findByText("已保存为版本 2。")).toBeInTheDocument();
  const saveBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as {
    expected_version: number;
  };
  expect(saveBody.expected_version).toBe(1);

  await user.click(screen.getByRole("button", { name: "校验" }));
  expect(await screen.findByText("没有发现阻塞问题。")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "提升为正式修订" }));
  expect(
    await screen.findByText(
      "已生成 wechat-add-friend 的正式修订 #1，尚未公开发布。",
    ),
  ).toBeInTheDocument();
  const promoteBody = JSON.parse(
    String(fetchMock.mock.calls[2]?.[1]?.body),
  ) as {
    expected_version: number;
  };
  expect(promoteBody.expected_version).toBe(2);
});

it("explains an optimistic-lock conflict instead of overwriting", async () => {
  const user = userEvent.setup();
  fetchMock.mockResolvedValueOnce(
    jsonResponse({ detail: { message: "changed", current_version: 2 } }, 409),
  );
  render(
    <WorkspaceEditor
      initialWorkspace={workspace(1)}
      onBack={vi.fn()}
      onUnauthorized={vi.fn()}
    />,
  );

  fireEvent.change(screen.getByLabelText("教程工作区文档"), {
    target: { value: formatDocument(workspace().document) + "\n" },
  });
  await user.click(screen.getByRole("button", { name: "保存" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("其他页面被更新");
});
