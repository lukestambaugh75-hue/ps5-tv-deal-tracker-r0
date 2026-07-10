const VALID_VIEWS = new Set(["compact", "details"]);
const ACTIONABLE_STATES = new Set(["Fresh", "Due"]);
const SUCCESSFUL_ATTEMPTS = new Set(["success", "unknown"]);

function normalized(value) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function finiteDate(value) {
  const timestamp = Date.parse(value || "");
  return Number.isFinite(timestamp) ? timestamp : null;
}

export function parseView(search = "") {
  const value = new URLSearchParams(String(search).replace(/^\?/, "")).get("view");
  return VALID_VIEWS.has(value) ? value : "compact";
}

export function setViewQuery(search = "", view = "compact") {
  const parameters = new URLSearchParams(String(search).replace(/^\?/, ""));
  if (view === "details") {
    parameters.set("view", "details");
  } else {
    parameters.delete("view");
  }
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

export function applyRowControls(rows, controls = {}) {
  const target = normalized(controls.target);
  const retailer = normalized(controls.retailer);
  const status = normalized(controls.status);
  const direction = normalized(controls.direction) === "desc" ? "desc" : "asc";

  return Array.from(rows || [], (row, index) => ({ row, index }))
    .filter(({ row }) => !target || normalized(row.target ?? row.target_id) === target)
    .filter(({ row }) => !retailer || normalized(row.retailer) === retailer)
    .filter(({ row }) => !status || normalized(row.status) === status)
    .sort((left, right) => {
      const leftPrice = Number(left.row.price);
      const rightPrice = Number(right.row.price);
      const leftFinite = Number.isFinite(leftPrice);
      const rightFinite = Number.isFinite(rightPrice);
      if (!leftFinite && !rightFinite) return left.index - right.index;
      if (!leftFinite) return 1;
      if (!rightFinite) return -1;
      const delta = leftPrice - rightPrice;
      return (direction === "desc" ? -delta : delta) || left.index - right.index;
    })
    .map(({ row }) => row);
}

export function formatAge(ageMinutes) {
  if (!Number.isFinite(ageMinutes)) return "Unknown";
  const total = Math.max(0, Math.floor(ageMinutes));
  const days = Math.floor(total / 1440);
  const hours = Math.floor((total % 1440) / 60);
  const minutes = total % 60;
  const parts = [];
  if (days) parts.push(`${days} day${days === 1 ? "" : "s"}`);
  if (hours) parts.push(`${hours} hour${hours === 1 ? "" : "s"}`);
  if (!parts.length || (!days && minutes)) {
    parts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`);
  }
  return parts.join(" ");
}

export function calculateRefreshState(refresh = {}, now = new Date()) {
  const archived = Boolean(refresh.archived);
  const successAt = finiteDate(refresh.data_refreshed_at_utc);
  const attemptAt = finiteDate(refresh.last_attempt_at_utc);
  const nowAt = now instanceof Date ? now.getTime() : finiteDate(now);
  const cadenceMinutes = Number(refresh.cadence_minutes || 2880);
  const graceMinutes = Number(refresh.grace_minutes || 180);
  const attemptStatus = normalized(refresh.last_attempt_status) || "unknown";
  const attemptReason = String(refresh.last_attempt_reason || "").trim();
  const elapsedMilliseconds = successAt !== null && nowAt !== null
    ? nowAt - successAt
    : null;
  const ageMinutes = elapsedMilliseconds === null
    ? null
    : Math.max(0, Math.floor(elapsedMilliseconds / 60000));
  const result = {
    state: "Unknown",
    reason: "No successful data refresh is recorded.",
    ageMinutes,
    ageLabel: formatAge(ageMinutes),
  };

  if (archived) {
    return {
      ...result,
      state: "Archived",
      reason: "This tracker is archived and no longer refreshes.",
    };
  }
  if (successAt === null || nowAt === null) return result;

  if (elapsedMilliseconds < 0) {
    return {
      ...result,
      reason: "The recorded data refresh is in the future.",
      ageMinutes: null,
      ageLabel: "Unknown",
    };
  }
  const ageLabel = formatAge(ageMinutes);
  if (
    !SUCCESSFUL_ATTEMPTS.has(attemptStatus)
    && attemptAt !== null
    && attemptAt > successAt
  ) {
    const detail = attemptReason || "The latest refresh attempt did not complete.";
    return {
      state: "Blocked",
      reason: `Latest attempt ${attemptStatus}: ${detail}`,
      ageMinutes,
      ageLabel,
    };
  }
  if (elapsedMilliseconds <= cadenceMinutes * 60000) {
    return {
      state: "Fresh",
      reason: "Data is within the 48-hour refresh cadence.",
      ageMinutes,
      ageLabel,
    };
  }
  if (elapsedMilliseconds <= (cadenceMinutes + Math.max(0, graceMinutes)) * 60000) {
    return {
      state: "Due",
      reason: "Data is due but remains inside the 3-hour grace window.",
      ageMinutes,
      ageLabel,
    };
  }
  return {
    state: "Stale",
    reason: "Data is older than the cadence and grace window.",
    ageMinutes,
    ageLabel,
  };
}

function applyRecommendationState(documentRoot, state, represented) {
  const actionable = represented && ACTIONABLE_STATES.has(state);
  const mode = actionable ? "fresh" : state === "Unknown" ? "unknown" : "historical";
  documentRoot.body.classList.toggle("recommendations-historical", !actionable);
  documentRoot.body.classList.toggle("recommendations-unverified", mode === "unknown");
  documentRoot
    .querySelectorAll(
      "[data-recommendation-label], [data-recommendation-summary], [data-retailer-heading], [data-row-metric]",
    )
    .forEach((node) => {
      node.textContent = mode === "fresh"
        ? node.dataset.freshText
        : mode === "unknown"
          ? node.dataset.unknownText
          : node.dataset.historicalText;
    });
  documentRoot.querySelectorAll("[data-recommendation-card]").forEach((card) => {
    card.classList.toggle("historical", mode === "historical");
    card.classList.toggle("unverified", mode === "unknown");
  });
  documentRoot.querySelectorAll("[data-fresh-treatment]").forEach((chip) => {
    chip.classList.toggle("good", mode === "fresh");
    chip.classList.toggle("historical", mode === "historical");
    chip.classList.toggle("unverified", mode === "unknown");
    chip.textContent = mode === "fresh"
      ? chip.dataset.freshText
      : mode === "unknown"
        ? chip.dataset.unknownText
        : chip.dataset.historicalText;
  });
  const warning = documentRoot.getElementById("historical-warning");
  if (warning) {
    warning.hidden = actionable;
    warning.textContent = mode === "unknown"
      ? warning.dataset.unknownText
      : warning.dataset.historicalText;
  }
}

export function hydrateRefreshState(root, now = new Date()) {
  if (!root) return null;
  const documentRoot = root.ownerDocument;
  const refresh = {
    data_refreshed_at_utc: root.dataset.successAt,
    last_attempt_at_utc: root.dataset.attemptAt,
    last_attempt_status: root.dataset.attemptStatus,
    last_attempt_reason: root.dataset.attemptReason,
    cadence_minutes: Number(root.dataset.cadenceMinutes || 0),
    grace_minutes: Number(root.dataset.graceMinutes || 0),
    archived: root.dataset.archived === "true",
  };
  const result = calculateRefreshState(refresh, now);
  const stateNode = documentRoot.getElementById("refresh-status");
  const heroStateNode = documentRoot.getElementById("hero-data-state");
  const ageNode = documentRoot.getElementById("refresh-age");
  const reasonNode = documentRoot.getElementById("refresh-reason");
  if (stateNode) {
    stateNode.textContent = result.state;
    stateNode.className = `state-badge ${result.state.toLocaleLowerCase()}`;
  }
  if (heroStateNode) heroStateNode.textContent = result.state;
  if (ageNode) ageNode.textContent = result.ageLabel;
  if (reasonNode) reasonNode.textContent = result.reason;
  applyRecommendationState(
    documentRoot,
    result.state,
    root.dataset.represented === "true",
  );
  return result;
}

function initializeView(documentRoot) {
  const setView = (view, updateQuery) => {
    const selected = VALID_VIEWS.has(view) ? view : "compact";
    documentRoot.body.dataset.dashboardView = selected;
    documentRoot.querySelectorAll("[data-view-control]").forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        button.dataset.viewControl === selected ? "true" : "false",
      );
    });
    documentRoot.querySelectorAll("[data-details-only]").forEach((panel) => {
      panel.hidden = selected !== "details";
    });
    if (updateQuery) {
      window.history.replaceState(
        null,
        "",
        setViewQuery(window.location.search, selected) + window.location.hash,
      );
    }
  };

  setView(parseView(window.location.search), false);
  documentRoot.querySelectorAll("[data-view-control]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.viewControl, true));
  });
}

function initializeRows(documentRoot) {
  const controls = documentRoot.querySelector("[data-row-controls]");
  const body = documentRoot.querySelector("[data-deal-table-body]");
  if (!controls || !body) return;
  const rows = Array.from(body.querySelectorAll("[data-deal-row]"), (node) => ({
    node,
    target: node.dataset.target,
    retailer: node.dataset.retailer,
    status: node.dataset.status,
    price: Number(node.dataset.price),
  }));
  const count = documentRoot.querySelector("[data-result-count]");
  const empty = documentRoot.querySelector("[data-empty-state]");
  const target = controls.querySelector("[data-filter-target]");
  const retailer = controls.querySelector("[data-filter-retailer]");
  const status = controls.querySelector("[data-filter-status]");
  const direction = controls.querySelector("[data-sort-direction]");

  const update = () => {
    const result = applyRowControls(rows, {
      target: target?.value,
      retailer: retailer?.value,
      status: status?.value,
      direction: direction?.value,
    });
    const visible = new Set(result);
    rows.forEach((row) => { row.node.hidden = !visible.has(row); });
    result.forEach((row) => body.appendChild(row.node));
    rows.filter((row) => !visible.has(row)).forEach((row) => body.appendChild(row.node));
    if (count) count.textContent = `${result.length} of ${rows.length} rows`;
    if (empty) empty.hidden = result.length !== 0;
  };

  controls.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", update);
  });
  update();
}

export function initializeDashboard(documentRoot = document) {
  initializeView(documentRoot);
  initializeRows(documentRoot);
  const refreshRoot = documentRoot.querySelector("[data-refresh-root]");
  if (refreshRoot) {
    hydrateRefreshState(refreshRoot);
    window.setInterval(() => hydrateRefreshState(refreshRoot), 60000);
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initializeDashboard(document));
  } else {
    initializeDashboard(document);
  }
}
