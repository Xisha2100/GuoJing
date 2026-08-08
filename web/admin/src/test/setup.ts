import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  document.cookie = "guojing_admin_csrf=; Max-Age=0; Path=/";
});
