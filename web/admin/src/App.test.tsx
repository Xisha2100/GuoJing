import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import App from "./App";
import { adminSession, jsonResponse } from "./test/fixtures";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

it("moves from an expired session to login and the workspace dashboard", async () => {
  fetchMock
    .mockResolvedValueOnce(
      jsonResponse({ detail: "administrator login is required" }, 401),
    )
    .mockResolvedValueOnce(jsonResponse(adminSession))
    .mockResolvedValueOnce(jsonResponse([]));
  const user = userEvent.setup();
  render(<App />);

  await user.type(await screen.findByLabelText("用户名"), "family-admin");
  await user.type(screen.getByLabelText("密码"), "correct-password");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(
    await screen.findByRole("heading", { name: "教程工作区" }),
  ).toBeInTheDocument();
  expect(screen.getByText("管理员：family-admin")).toBeInTheDocument();
  const loginCall = fetchMock.mock.calls[1];
  expect(loginCall?.[0]).toBe("/api/v1/admin/auth/login");
  expect(loginCall?.[1]?.body).toBe(
    JSON.stringify({ username: "family-admin", password: "correct-password" }),
  );
});

it("shows a generic backend login error without exposing implementation details", async () => {
  fetchMock
    .mockResolvedValueOnce(
      jsonResponse({ detail: "administrator login is required" }, 401),
    )
    .mockResolvedValueOnce(
      jsonResponse({ detail: "invalid username or password" }, 401),
    );
  const user = userEvent.setup();
  render(<App />);

  await user.type(await screen.findByLabelText("用户名"), "unknown-admin");
  await user.type(screen.getByLabelText("密码"), "wrong-password");
  await user.click(screen.getByRole("button", { name: "登录" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "invalid username or password",
  );
});

it("restores an existing session and logs out with CSRF proof", async () => {
  document.cookie = "guojing_admin_csrf=logout-csrf; Path=/";
  fetchMock
    .mockResolvedValueOnce(jsonResponse(adminSession))
    .mockResolvedValueOnce(jsonResponse([]))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "退出登录" }));

  expect(
    await screen.findByRole("heading", { name: "管理员登录" }),
  ).toBeInTheDocument();
  const logoutCall = fetchMock.mock.calls[2];
  expect(logoutCall?.[0]).toBe("/api/v1/admin/auth/logout");
  expect(new Headers(logoutCall?.[1]?.headers).get("X-CSRF-Token")).toBe(
    "logout-csrf",
  );
});
