import test from "node:test";
import assert from "node:assert/strict";

import {
  applyRowControls,
  calculateRefreshState,
  hydrateRefreshState,
  parseView,
  setViewQuery,
} from "../assets/dashboard-ui.mjs";

const rows = Object.freeze([
  Object.freeze({ target: "ps5", retailer: "Best Buy", status: "in_stock", price: 499.99 }),
  Object.freeze({ target: "tv", retailer: "Costco", status: "limited", price: 899.99 }),
  Object.freeze({ target: "tv", retailer: "Best Buy", status: "in_stock", price: 699.99 }),
]);

test("parseView defaults to compact and accepts details", () => {
  assert.equal(parseView(""), "compact");
  assert.equal(parseView("?view=compact"), "compact");
  assert.equal(parseView("?view=details"), "details");
  assert.equal(parseView("?view=unsupported"), "compact");
});

test("setViewQuery preserves unrelated query parameters", () => {
  assert.equal(setViewQuery("?utm=email", "details"), "?utm=email&view=details");
  assert.equal(setViewQuery("?view=details&utm=email", "compact"), "?utm=email");
});

test("composed filters and ascending price sort work without mutating source rows", () => {
  const snapshot = JSON.stringify(rows);
  const actual = applyRowControls(rows, {
    target: "tv",
    retailer: "Best Buy",
    status: "in_stock",
    direction: "asc",
  });
  assert.deepEqual(actual.map((row) => row.price), [699.99]);
  assert.equal(JSON.stringify(rows), snapshot);
});

test("both price sort directions are explicit and stable", () => {
  assert.deepEqual(
    applyRowControls(rows, { direction: "asc" }).map((row) => row.price),
    [499.99, 699.99, 899.99],
  );
  assert.deepEqual(
    applyRowControls(rows, { direction: "desc" }).map((row) => row.price),
    [899.99, 699.99, 499.99],
  );
});

test("refresh state calculation matches every Python freshness boundary", () => {
  const refresh = {
    data_refreshed_at_utc: "2026-07-10T12:00:00Z",
    last_attempt_at_utc: "2026-07-10T12:00:00Z",
    last_attempt_status: "success",
    cadence_minutes: 60,
    grace_minutes: 30,
    archived: false,
  };
  assert.equal(
    calculateRefreshState(refresh, new Date("2026-07-10T13:00:00Z")).state,
    "Fresh",
  );
  assert.equal(
    calculateRefreshState(refresh, new Date("2026-07-10T13:00:01Z")).state,
    "Due",
  );
  assert.equal(
    calculateRefreshState(refresh, new Date("2026-07-10T13:30:00Z")).state,
    "Due",
  );
  assert.equal(
    calculateRefreshState(refresh, new Date("2026-07-10T13:30:01Z")).state,
    "Stale",
  );
  assert.equal(
    calculateRefreshState({}, new Date("2026-07-10T13:00:00Z")).state,
    "Unknown",
  );
  assert.equal(
    calculateRefreshState(
      { ...refresh, data_refreshed_at_utc: "2026-07-10T14:00:00Z" },
      new Date("2026-07-10T13:00:00Z"),
    ).state,
    "Unknown",
  );
});

test("refresh blocks only when an unsuccessful attempt is strictly newer", () => {
  const refresh = {
    data_refreshed_at_utc: "2026-07-10T12:00:00Z",
    last_attempt_at_utc: "2026-07-10T12:00:00Z",
    last_attempt_status: "failed",
    cadence_minutes: 60,
    grace_minutes: 30,
    archived: false,
  };
  assert.equal(
    calculateRefreshState(refresh, new Date("2026-07-10T12:30:00Z")).state,
    "Fresh",
  );
  assert.equal(
    calculateRefreshState(
      { ...refresh, last_attempt_at_utc: "2026-07-10T12:00:01Z" },
      new Date("2026-07-10T12:30:00Z"),
    ).state,
    "Blocked",
  );
});

test("refresh hydration applies the calculated state to the generated nodes", () => {
  const nodes = new Map([
    ["refresh-status", { textContent: "", className: "" }],
    ["hero-data-state", { textContent: "" }],
    ["refresh-age", { textContent: "" }],
    ["refresh-reason", { textContent: "" }],
  ]);
  const documentRoot = {
    body: { classList: { toggle() {} } },
    getElementById(id) { return nodes.get(id) ?? null; },
    querySelectorAll() { return []; },
  };
  const root = {
    ownerDocument: documentRoot,
    dataset: {
      successAt: "2026-07-10T12:00:00Z",
      attemptAt: "2026-07-10T12:00:00Z",
      attemptStatus: "success",
      attemptReason: "",
      cadenceMinutes: "60",
      graceMinutes: "30",
      archived: "false",
      represented: "true",
    },
  };

  const result = hydrateRefreshState(root, new Date("2026-07-10T12:30:00Z"));

  assert.equal(result.state, "Fresh");
  assert.equal(nodes.get("refresh-status").textContent, "Fresh");
  assert.equal(nodes.get("refresh-status").className, "state-badge fresh");
  assert.equal(nodes.get("hero-data-state").textContent, "Fresh");
  assert.equal(nodes.get("refresh-age").textContent, "30 minutes");
});
