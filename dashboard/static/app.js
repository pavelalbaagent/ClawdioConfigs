const state = {
  snapshot: null,
  refreshTimer: null,
  loading: false,
};

const PROJECT_STATUSES = ["active", "planned", "paused", "blocked", "done", "archived"];
const TASK_STATUSES = ["todo", "in_progress", "blocked", "done"];
const RUN_TERMINAL_STATUSES = ["succeeded", "failed", "cancelled"];

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = byId(id);
  if (el) {
    el.textContent = value;
  }
}

function showError(message) {
  const banner = byId("error-banner");
  if (!banner) {
    return;
  }
  if (!message) {
    banner.classList.remove("visible");
    banner.textContent = "";
    return;
  }
  banner.textContent = message;
  banner.classList.add("visible");
}

function setHealth(ok, label) {
  const pill = byId("health-pill");
  if (!pill) {
    return;
  }
  const dot = pill.querySelector(".status-dot");
  pill.lastChild.textContent = ` ${label}`;
  if (dot) {
    dot.classList.toggle("ok", ok);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const payload = await response.json().catch(() => ({}));

  if (response.status === 401) {
    window.location.href = "/login.html";
    throw new Error("unauthorized");
  }

  if (!response.ok) {
    const message = payload.error || `HTTP ${response.status}`;
    throw new Error(message);
  }

  return payload;
}

function formatUsd(value) {
  const num = Number(value || 0);
  return `$${num.toFixed(4)}`;
}

function formatInt(value) {
  return Number(value || 0).toLocaleString();
}

function createToggleItem({ title, meta, enabled, onToggle }) {
  const row = document.createElement("div");
  row.className = "list-item";

  const text = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  text.appendChild(strong);

  if (meta) {
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = meta;
    text.appendChild(metaEl);
  }

  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.className = "toggle";
  toggle.checked = Boolean(enabled);
  toggle.addEventListener("change", async () => {
    toggle.disabled = true;
    try {
      await onToggle(toggle.checked);
      await loadState();
    } catch (error) {
      toggle.checked = !toggle.checked;
      showError(error.message);
    } finally {
      toggle.disabled = false;
    }
  });

  row.appendChild(text);
  row.appendChild(toggle);
  return row;
}

function appendCells(tr, values) {
  for (const value of values) {
    const td = document.createElement("td");
    td.textContent = value;
    tr.appendChild(td);
  }
}

function parseCommaList(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function currentProjects() {
  return (((state.snapshot || {}).workspace || {}).projects || []).slice();
}

function promptForProjectSelection(currentProjectId = "") {
  const projects = currentProjects().filter((project) => project.status !== "archived");
  if (!projects.length) {
    throw new Error("No project spaces are available.");
  }

  const defaultProject = projects.find((project) => project.id === currentProjectId) || projects[0];
  const options = projects.map((project, index) => {
    const currentTag = project.id === currentProjectId ? " [current]" : "";
    return `${index + 1}. ${project.name} (${project.space_key || project.id})${currentTag}`;
  });

  const raw = window.prompt(
    `Choose project by number, project id, or space key:\n${options.join("\n")}`,
    defaultProject.space_key || defaultProject.id
  );
  if (raw === null) {
    return null;
  }

  const clean = raw.trim();
  if (!clean) {
    throw new Error("Project selection is required.");
  }

  const numericIndex = Number(clean);
  if (Number.isInteger(numericIndex) && numericIndex >= 1 && numericIndex <= projects.length) {
    return projects[numericIndex - 1];
  }

  const lowered = clean.toLowerCase();
  const direct = projects.find(
    (project) =>
      project.id.toLowerCase() === lowered ||
      String(project.space_key || "").toLowerCase() === lowered ||
      project.name.toLowerCase() === lowered
  );
  if (direct) {
    return direct;
  }

  throw new Error(`Unknown project selection: ${clean}`);
}

function renderProfiles(snapshot) {
  const intSelect = byId("integration-profile-select");
  const memSelect = byId("memory-profile-select");

  intSelect.innerHTML = "";
  memSelect.innerHTML = "";

  for (const name of snapshot.profiles.integrations.definitions || []) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    option.selected = name === snapshot.profiles.integrations.active;
    intSelect.appendChild(option);
  }

  for (const name of snapshot.profiles.memory.definitions || []) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    option.selected = name === snapshot.profiles.memory.active;
    memSelect.appendChild(option);
  }
}

function renderPresets(snapshot) {
  const list = byId("preset-list");
  list.innerHTML = "";

  for (const preset of snapshot.presets || []) {
    const row = document.createElement("div");
    row.className = "list-item";

    const left = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = preset.name;
    left.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = preset.description || "Preset pack";
    left.appendChild(meta);

    const btn = document.createElement("button");
    btn.className = "secondary";
    btn.textContent = "Apply";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const result = await api("/api/presets/apply", {
          method: "POST",
          body: { name: preset.name },
        });
        setText("preset-status", `Applied ${preset.name}. ${result.result.actions.join(", ")}`);
        await loadState();
      } catch (error) {
        showError(error.message);
      } finally {
        btn.disabled = false;
      }
    });

    row.appendChild(left);
    row.appendChild(btn);
    list.appendChild(row);
  }
}

function renderAdapters(snapshot) {
  const list = byId("adapter-list");
  list.innerHTML = "";

  const cfg = snapshot.dashboard.dashboard || {};
  const adapters = cfg.adapters || {};
  const auth = cfg.auth || {};
  const routing = snapshot.routing || {};

  const adapterRows = [
    {
      key: "local_telemetry_enabled",
      title: "Local telemetry parser",
      meta: "Reads telemetry/model-calls*.ndjson",
    },
    {
      key: "codexbar_cost_enabled",
      title: "Codexbar cost adapter",
      meta: "Runs codexbar cost --format json",
    },
    {
      key: "codexbar_usage_enabled",
      title: "Codexbar usage adapter",
      meta: "Runs codexbar usage --format json",
    },
  ];

  for (const row of adapterRows) {
    list.appendChild(
      createToggleItem({
        title: row.title,
        meta: row.meta,
        enabled: adapters[row.key],
        onToggle: (enabled) => api("/api/dashboard/settings", { method: "POST", body: { [row.key]: enabled } }),
      })
    );
  }

  byId("codexbar-provider-select").value = (cfg.codexbar || {}).provider || "all";
  const modeSelect = byId("routing-mode-select");
  modeSelect.innerHTML = "";
  const modeRows = routing.modes || [];
  if (modeRows.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "no modes";
    modeSelect.appendChild(option);
  } else {
    for (const mode of modeRows) {
      const option = document.createElement("option");
      option.value = mode.name;
      option.textContent = mode.name;
      if (mode.description) {
        option.title = mode.description;
      }
      option.selected = mode.name === routing.active_mode;
      modeSelect.appendChild(option);
    }
  }
  byId("refresh-seconds-input").value = Number((cfg.ui || {}).auto_refresh_seconds || 20);
  byId("auth-required-toggle").checked = Boolean(auth.require_token);
  byId("auth-env-key-input").value = auth.token_env_key || "OPENCLAW_DASHBOARD_TOKEN";
  byId("auth-allow-generated-toggle").checked = Boolean(auth.allow_generated_token);
}

function renderMetrics(snapshot) {
  const enabledIntegrations = (snapshot.modules.integrations || []).filter((row) => row.enabled).length;
  const workspace = snapshot.workspace || {};
  const progress = workspace.progress || {};
  const taskCounts = workspace.task_counts || {};

  const openTasks = Number(taskCounts.todo || 0) + Number(taskCounts.in_progress || 0) + Number(taskCounts.blocked || 0);

  setText("metric-integration-profile", snapshot.profiles.integrations.active || "-");
  setText("metric-integration-count", `${enabledIntegrations} enabled`);

  setText("metric-open-tasks", formatInt(openTasks));
  setText("metric-task-progress", `${formatInt(progress.task_done || 0)} done / ${formatInt(progress.task_total || 0)} total`);

  setText("metric-projects", formatInt(progress.active_projects || 0));
  setText("metric-project-progress", `${formatInt(progress.task_completion_pct || 0)}% completion`);

  const pendingReminders = (snapshot.reminders.pending_items || []).length;
  setText("metric-reminders", formatInt(pendingReminders));

  const missingEnv = (snapshot.env.missing || []).length;
  setHealth(missingEnv === 0, missingEnv === 0 ? "ready" : `${missingEnv} env gaps`);
}

function renderIntegrationLists(snapshot) {
  const integrationsList = byId("integrations-list");
  const memoryList = byId("memory-list");
  const n8nList = byId("n8n-list");

  integrationsList.innerHTML = "";
  memoryList.innerHTML = "";
  n8nList.innerHTML = "";

  for (const row of snapshot.modules.integrations || []) {
    integrationsList.appendChild(
      createToggleItem({
        title: row.name,
        meta: `${row.execution_mode} | provider: ${row.provider} | cost: ${row.cost_class}`,
        enabled: row.enabled,
        onToggle: (enabled) => api("/api/integrations/toggle", { method: "POST", body: { name: row.name, enabled } }),
      })
    );
  }

  for (const row of snapshot.modules.memory || []) {
    memoryList.appendChild(
      createToggleItem({
        title: row.name,
        meta: `${row.required_env_count} required env vars`,
        enabled: row.enabled,
        onToggle: (enabled) => api("/api/memory/toggle", { method: "POST", body: { name: row.name, enabled } }),
      })
    );
  }

  for (const row of snapshot.modules.n8n || []) {
    n8nList.appendChild(
      createToggleItem({
        title: row.name,
        meta: "n8n submodule",
        enabled: row.enabled,
        onToggle: (enabled) => api("/api/n8n/toggle", { method: "POST", body: { name: row.name, enabled } }),
      })
    );
  }
}

function renderProviderHealth(snapshot) {
  const providerBody = byId("provider-health-body");
  const routingBody = byId("provider-routing-body");
  providerBody.innerHTML = "";
  routingBody.innerHTML = "";

  const health = snapshot.provider_health || {};
  const summary = health.summary || {};
  const profiles = health.active_profiles || {};
  const providers = health.providers || [];
  const situations = health.situations || [];

  setText(
    "provider-health-summary",
    `${summary.configured_count || 0}/${summary.total_providers || 0} configured | ${summary.locally_usable_count || 0} locally usable | ${summary.live_ok_count || 0} live ok`
  );
  setText(
    "provider-health-profiles-meta",
    `integrations=${profiles.integrations || "-"} | memory=${profiles.memory || "-"} | routing=${profiles.routing_mode || "-"}`
  );
  setText("provider-health-last-probe-meta", health.last_snapshot_generated_at || "not run");
  setText("provider-health-env-meta", health.env_file || "not found");

  if (!providers.length) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-", "-"]);
    providerBody.appendChild(tr);
  } else {
    for (const row of providers) {
      const tr = document.createElement("tr");
      const localStatus = row.local_status === "ready"
        ? "ready"
        : row.local_status === "missing_env"
          ? `missing env: ${(row.missing_env || []).join(", ")}`
          : row.local_status === "missing_command"
            ? `missing command: ${row.required_command || "-"}`
            : row.local_status || "-";
      const probe = row.live_probe || {};
      let liveStatus = "-";
      if (probe.attempted) {
        liveStatus = probe.ok ? `ok (${probe.latency_ms || 0}ms)` : `error: ${probe.error || "failed"}`;
      } else if (row.configured) {
        liveStatus = "not run";
      }
      const usedBy = [];
      if ((row.referenced_by_lanes || []).length) {
        usedBy.push((row.referenced_by_lanes || []).join(", "));
      }
      if (row.enabled_in_active_memory) {
        usedBy.push("memory");
      }
      appendCells(tr, [
        row.provider || "-",
        row.resolved_default_model || row.default_model || "-",
        localStatus,
        liveStatus,
        usedBy.join(" | ") || "-",
      ]);
      providerBody.appendChild(tr);
    }
  }

  if (!situations.length) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-"]);
    routingBody.appendChild(tr);
    return;
  }

  for (const row of situations) {
    const tr = document.createElement("tr");
    const candidates = (row.provider_candidates || [])
      .map((candidate) => `${candidate.provider}[${candidate.model || "-"}]`)
      .join(", ");
    appendCells(tr, [
      row.name || "-",
      row.preferred_lane || "-",
      candidates || "-",
      row.approval_required ? "yes" : "no",
    ]);
    routingBody.appendChild(tr);
  }
}

function renderAgentRuntime(snapshot) {
  const runtime = snapshot.agent_runtime || {};
  const registryBody = byId("agent-registry-body");
  registryBody.innerHTML = "";

  const visibleAgents = runtime.visible_agents || [];
  const internalRoles = runtime.internal_roles || [];
  const activity = runtime.activity || {};
  const improvement = runtime.continuous_improvement || {};
  const sessionPolicy = runtime.session_policy || {};
  const spaceRegistry = runtime.space_registry || {};
  const lastRoute = activity.last_route || null;
  const routeCounts = activity.counts_by_agent || {};
  const routeSpaceCounts = activity.counts_by_space || {};

  setText(
    "agent-runtime-summary",
    `${visibleAgents.length} visible agents | ${internalRoles.length} internal roles | routing=${runtime.active_routing_mode || "-"}`
  );
  setText(
    "agent-default-meta",
    `${runtime.default_user_facing_agent || "assistant"} | summarize>${sessionPolicy.summarize_when_context_tokens_over || "-"} | idle reset=${sessionPolicy.idle_reset_minutes || "-"}m`
  );
  setText(
    "agent-space-grammar-meta",
    (spaceRegistry.catalog || [])
      .map((row) => row.entry_command_hint || row.key)
      .slice(0, 8)
      .join(" | ") || "-"
  );
  setText(
    "agent-route-counts-meta",
    Object.entries(routeCounts)
      .map(([agent, count]) => `${agent}=${count}`)
      .join(" | ") || "no routed activity yet"
  );

  if (!visibleAgents.length) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-", "-"]);
    registryBody.appendChild(tr);
  } else {
    for (const row of visibleAgents) {
      const tr = document.createElement("tr");
      appendCells(tr, [
        row.label || row.id || "-",
        row.default_space || "-",
        row.default_lane || "-",
        (row.owned_spaces || []).join(", ") || "-",
        (row.responsibilities || []).slice(0, 3).join(", ") || "-",
      ]);
      registryBody.appendChild(tr);
    }
  }

  if (!lastRoute) {
    setText("agent-last-route-meta", "No routed interactions yet.");
  } else {
    const parts = [
      `${lastRoute.agent_label || lastRoute.agent_id || "-"}`,
      `space=${lastRoute.space_key || "-"}`,
      `mode=${lastRoute.route_mode || "-"}`,
      `source=${lastRoute.source || "-"}`,
    ];
    if (lastRoute.project_name) {
      parts.push(`project=${lastRoute.project_name}`);
    }
    if (lastRoute.action) {
      parts.push(`action=${lastRoute.action}`);
    }
    if (lastRoute.excerpt) {
      parts.push(`text=${lastRoute.excerpt}`);
    }
    setText("agent-last-route-meta", parts.join(" | "));
  }

  setText(
    "agent-internal-roles-meta",
    internalRoles.map((row) => `${row.label || row.id}(${row.default_lane || "-"})`).join(" | ") || "-"
  );

  const cadence = improvement.cadence || {};
  setText(
    "agent-improvement-meta",
    improvement.enabled
      ? `${improvement.owner_role || "ops_guard"} | daily=${cadence.daily_ops_review ? "on" : "off"} | weekly=${
          cadence.weekly_architecture_review ? "on" : "off"
        }`
      : "disabled"
  );
  setText(
    "agent-blocked-actions-meta",
    (improvement.blocked_auto_actions || []).join(", ") || "none"
  );
  setText(
    "agent-recent-routes-meta",
    (activity.recent_routes || [])
      .slice()
      .reverse()
      .map((row) => `${row.agent_id || "-"}:${row.space_key || "-"}${row.task_id ? ` -> ${row.task_id}` : ""}`)
      .slice(0, 6)
      .join(" | ") ||
      Object.entries(routeSpaceCounts)
        .map(([space, count]) => `${space}=${count}`)
        .join(" | ") ||
      "none"
  );

  const assistantChat = snapshot.assistant_chat || {};
  if (!assistantChat.available) {
    setText("assistant-chat-meta", "No assistant chat state yet.");
    return;
  }
  setText(
    "assistant-chat-meta",
    (assistantChat.spaces || [])
      .map(
        (row) =>
          `${row.space_key || "-"}:${row.turn_count || 0}t${
            row.last_lane ? ` | ${row.last_lane}` : ""
          }${row.last_provider ? ` | ${row.last_provider}` : ""}`
      )
      .slice(0, 4)
      .join(" | ") || "No assistant chat sessions yet."
  );
}

function renderReminders(snapshot) {
  const body = byId("reminders-body");
  body.innerHTML = "";

  const pending = snapshot.reminders.pending_items || [];
  if (pending.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const row of pending) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      row.message || "-",
      row.status || "-",
      row.remind_at || "-",
      row.minutes_until != null ? String(row.minutes_until) : "-",
      row.next_followup_at || "-",
    ]);
    body.appendChild(tr);
  }
}

function renderTodoQueue(snapshot) {
  const body = byId("todo-queue-body");
  body.innerHTML = "";

  const rows = snapshot.workspace.todo_queue || [];
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const row of rows.slice(0, 30)) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      row.title || "-",
      row.source || "-",
      row.status || "-",
      (row.assignees || []).join(", ") || "-",
      row.project_name || "-",
      row.due_at || "-",
    ]);
    body.appendChild(tr);
  }
}

function renderGmailInbox(snapshot) {
  const body = byId("gmail-body");
  body.innerHTML = "";

  const gmail = snapshot.gmail_inbox || {};
  if (!gmail.available) {
    setText("gmail-status-summary", "No Gmail inbox status file yet.");
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  const summary = gmail.summary || {};
  const promotions = gmail.promotions || {};
  const taskPromotions = promotions.tasks || {};
  const calendarPromotions = promotions.calendar || {};
  setText(
    "gmail-status-summary",
    `run=${gmail.run_id || "-"} | dry_run=${gmail.dry_run ? "yes" : "no"} | processed=${summary.processed_count || 0} | manual_review_open=${gmail.manual_review_open || 0} | task_promotions=${(taskPromotions.created || 0) + (taskPromotions.updated || 0)} | calendar_promotions=${(calendarPromotions.created || 0) + (calendarPromotions.updated || 0)}`
  );

  const rows = gmail.recent_results || [];
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const row of rows.slice(0, 20)) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      row.from_email || "-",
      row.subject || "-",
      row.primary_action || "-",
      row.reason || "-",
    ]);
    body.appendChild(tr);
  }
}

function renderDriveWorkspace(snapshot) {
  const drive = snapshot.drive_workspace || {};
  const summary = drive.summary || {};
  const root = summary.root || {};

  if (!drive.available) {
    setText("drive-root-meta", "No Drive workspace check yet.");
    setText("drive-missing-meta", "-");
    setText("drive-extra-meta", "-");
    setText("drive-checked-meta", "-");
    return;
  }

  setText("drive-root-meta", `${root.name || "-"} (${root.id || "-"})`);
  setText("drive-missing-meta", (summary.missing || []).join(", ") || "none");
  setText("drive-extra-meta", (summary.extra || []).join(", ") || "none");
  setText("drive-checked-meta", drive.generated_at || "-");
}

function renderCalendarRuntime(snapshot) {
  const body = byId("calendar-runtime-body");
  body.innerHTML = "";

  const runtime = snapshot.calendar_runtime || {};
  if (!runtime.available) {
    setText("calendar-runtime-summary", "No calendar runtime status file yet.");
    setText("calendar-runtime-updated-meta", "-");
    setText("calendar-runtime-candidates-meta", "-");
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  const summary = runtime.summary || {};
  setText(
    "calendar-runtime-summary",
    `action=${summary.action || "-"} | dry_run=${summary.dry_run ? "yes" : "no"} | upcoming=${summary.upcoming_count || 0} | created=${summary.created_count || 0} | updated=${summary.updated_count || 0} | skipped=${summary.skipped_count || 0} | errors=${summary.error_count || 0}`
  );
  setText("calendar-runtime-updated-meta", runtime.generated_at || "-");
  setText(
    "calendar-runtime-candidates-meta",
    summary.pending_candidate_count === undefined ? "-" : String(summary.pending_candidate_count)
  );

  const rows = runtime.upcoming_events || [];
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const row of rows.slice(0, 20)) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      row.summary || "-",
      row.start_value || "-",
      row.end_value || "-",
      row.all_day ? "all_day" : "timed",
      row.status || "-",
    ]);
    body.appendChild(tr);
  }
}

function calendarCandidateAttendees(item) {
  const attendees = item.attendees || [];
  const out = [];
  for (const entry of attendees) {
    if (typeof entry === "string" && entry.trim()) {
      out.push(entry.trim());
      continue;
    }
    if (entry && typeof entry === "object" && typeof entry.email === "string" && entry.email.trim()) {
      out.push(entry.email.trim());
    }
  }
  return out;
}

function calendarCandidateWhenLabel(item) {
  if (item.start_at || item.end_at) {
    return `${item.start_at || "?"} -> ${item.end_at || "?"}`;
  }
  if (item.start_date || item.end_date) {
    return `${item.start_date || "?"} -> ${item.end_date || "?"}`;
  }
  return item.context_ts || "-";
}

async function editCalendarCandidate(item) {
  const timezoneDefault = item.timezone || (((state.snapshot || {}).owner || {}).timezone) || "UTC";
  const titleValue = window.prompt("Calendar title", item.title || item.subject || "");
  if (titleValue === null) {
    return;
  }

  const modeDefault = item.start_date ? "all_day" : "timed";
  const modeValue = window.prompt("Mode: timed or all_day", modeDefault);
  if (modeValue === null) {
    return;
  }
  const mode = modeValue.trim().toLowerCase() === "all_day" ? "all_day" : "timed";

  const timezoneValue = window.prompt("Timezone", timezoneDefault);
  if (timezoneValue === null) {
    return;
  }
  const locationValue = window.prompt("Location", item.location || "");
  if (locationValue === null) {
    return;
  }
  const descriptionValue = window.prompt("Description", item.description || item.excerpt || "");
  if (descriptionValue === null) {
    return;
  }
  const attendeesValue = window.prompt("Attendees (comma list)", calendarCandidateAttendees(item).join(", "));
  if (attendeesValue === null) {
    return;
  }

  const body = {
    candidate_id: item.id,
    title: titleValue.trim(),
    timezone: timezoneValue.trim(),
    location: locationValue.trim(),
    description: descriptionValue.trim(),
    attendees: parseCommaList(attendeesValue || ""),
    start_at: "",
    end_at: "",
    start_date: "",
    end_date: "",
  };

  if (mode === "all_day") {
    const startDateValue = window.prompt("Start date (YYYY-MM-DD)", item.start_date || "");
    if (startDateValue === null) {
      return;
    }
    const endDateValue = window.prompt(
      "End date (YYYY-MM-DD, optional exclusive end)",
      item.end_date || ""
    );
    if (endDateValue === null) {
      return;
    }
    body.start_date = startDateValue.trim();
    body.end_date = endDateValue.trim();
  } else {
    const startAtValue = window.prompt("Start datetime (ISO8601)", item.start_at || "");
    if (startAtValue === null) {
      return;
    }
    const endAtValue = window.prompt("End datetime (ISO8601)", item.end_at || "");
    if (endAtValue === null) {
      return;
    }
    body.start_at = startAtValue.trim();
    body.end_at = endAtValue.trim();
  }

  const hasSchedule = Boolean(body.start_at || body.start_date);
  body.status = item.status === "scheduled" ? "scheduled" : hasSchedule ? "ready" : "needs_details";

  const result = await api("/api/calendar_candidates/update", {
    method: "POST",
    body,
  });
  setText("project-status", `Calendar candidate updated: ${result.result.item.title || item.title || item.id}.`);
  await loadState();
}

async function updateCalendarCandidateStatus(item, status) {
  const result = await api("/api/calendar_candidates/update", {
    method: "POST",
    body: {
      candidate_id: item.id,
      status,
    },
  });
  setText("project-status", `Calendar candidate set to ${result.result.item.status}.`);
  await loadState();
}

async function applyApprovedCalendarCandidates() {
  const result = await api("/api/calendar_candidates/apply", {
    method: "POST",
    body: {
      apply: true,
    },
  });
  const summary = ((result || {}).result || {}).status || {};
  const counts = summary.summary || {};
  setText(
    "project-status",
    `Calendar apply finished: created=${counts.created_count || 0}, updated=${counts.updated_count || 0}, skipped=${counts.skipped_count || 0}, errors=${counts.error_count || 0}.`
  );
  await loadState();
}

function renderCalendarCandidates(snapshot) {
  const body = byId("calendar-candidates-body");
  body.innerHTML = "";

  const calendar = snapshot.calendar_candidates || {};
  const items = calendar.items || [];
  if (!calendar.available) {
    setText("calendar-candidates-summary", "No calendar candidate file yet.");
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  const counts = calendar.status_counts || {};
  const countParts = Object.entries(counts).map(([key, value]) => `${key}=${value}`);
  setText(
    "calendar-candidates-summary",
    `${calendar.count || 0} candidates${countParts.length ? ` | ${countParts.join(", ")}` : ""}`
  );

  if (items.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const item of items.slice(0, 30)) {
    const tr = document.createElement("tr");
    const projectLabel = item.project_name || item.space_key || "-";
    appendCells(tr, [
      item.title || "-",
      calendarCandidateWhenLabel(item),
      item.from_email || "-",
      (item.intent_tags || []).join(", ") || "-",
      projectLabel,
      item.status || "-",
      item.updated_at || "-",
    ]);

    const actionsTd = document.createElement("td");
    const editBtn = document.createElement("button");
    editBtn.className = "secondary";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", async () => {
      editBtn.disabled = true;
      try {
        await editCalendarCandidate(item);
      } catch (error) {
        showError(error.message);
      } finally {
        editBtn.disabled = false;
      }
    });
    actionsTd.appendChild(editBtn);

    const approveBtn = document.createElement("button");
    approveBtn.className = "secondary";
    approveBtn.textContent = item.status === "approved" ? "Approved" : "Approve";
    approveBtn.disabled = item.status === "approved" || item.status === "scheduled";
    approveBtn.addEventListener("click", async () => {
      approveBtn.disabled = true;
      try {
        await updateCalendarCandidateStatus(item, "approved");
      } catch (error) {
        showError(error.message);
      } finally {
        approveBtn.disabled = item.status === "approved" || item.status === "scheduled";
      }
    });
    actionsTd.appendChild(approveBtn);

    const assignBtn = document.createElement("button");
    assignBtn.className = "secondary";
    assignBtn.textContent = item.project_id ? "Move" : "Project";
    assignBtn.addEventListener("click", async () => {
      assignBtn.disabled = true;
      try {
        const project = promptForProjectSelection(item.project_id || "");
        if (!project) {
          return;
        }
        const result = await api("/api/calendar_candidates/assign_project", {
          method: "POST",
          body: {
            candidate_id: item.id,
            project_id: project.id,
          },
        });
        setText(
          "project-status",
          `Calendar candidate routed to ${result.result.project.name} (${result.result.space.key}).`
        );
        await loadState();
      } catch (error) {
        showError(error.message);
      } finally {
        assignBtn.disabled = false;
      }
    });
    actionsTd.appendChild(assignBtn);
    tr.appendChild(actionsTd);
    body.appendChild(tr);
  }
}

function personalTaskDueLabel(task) {
  return task.due_value || task.due_string || "-";
}

function personalTaskDuePayload(raw) {
  const text = (raw || "").trim();
  if (!text) {
    return {};
  }
  if (/^\d{4}-\d{2}-\d{2}T/.test(text) || /[+-]\d{2}:\d{2}$/.test(text) || text.endsWith("Z")) {
    return { due_datetime: text };
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return { due_date: text };
  }
  return { due_string: text };
}

async function syncPersonalTasks() {
  const result = await api("/api/personal_tasks/sync", {
    method: "POST",
    body: {},
  });
  const summary = ((result || {}).result || {}).status || {};
  const counts = summary.summary || {};
  setText(
    "personal-task-action-status",
    `Personal tasks synced. Open=${counts.open_count || 0}, overdue=${counts.overdue_count || 0}.`
  );
  await loadState();
}

async function createPersonalTask() {
  const title = byId("personal-task-title-input").value.trim();
  if (!title) {
    throw new Error("personal task title is required");
  }
  const dueRaw = byId("personal-task-due-input").value.trim();
  const duePayload = personalTaskDuePayload(dueRaw);
  const priority = Number(byId("personal-task-priority-select").value || "2");

  await api("/api/personal_tasks/create", {
    method: "POST",
    body: {
      title,
      priority,
      apply: true,
      ...duePayload,
    },
  });

  byId("personal-task-title-input").value = "";
  byId("personal-task-due-input").value = "";
  byId("personal-task-priority-select").value = "2";
  setText("personal-task-action-status", "Personal task created.");
  await loadState();
}

async function completePersonalTask(task) {
  await api("/api/personal_tasks/complete", {
    method: "POST",
    body: {
      task_id: task.id,
      apply: true,
    },
  });
  setText("personal-task-action-status", `Completed personal task: ${task.title || task.id}.`);
  await loadState();
}

async function deferPersonalTask(task) {
  const value = window.prompt("New due date/time or natural language", task.due_value || task.due_string || "");
  if (value === null) {
    return;
  }
  const duePayload = personalTaskDuePayload(value);
  await api("/api/personal_tasks/defer", {
    method: "POST",
    body: {
      task_id: task.id,
      apply: true,
      ...duePayload,
    },
  });
  setText("personal-task-action-status", `Deferred personal task: ${task.title || task.id}.`);
  await loadState();
}

function renderPersonalTasks(snapshot) {
  const body = byId("personal-task-body");
  body.innerHTML = "";

  const personal = snapshot.personal_tasks || {};
  if (!personal.available) {
    setText("personal-task-summary", "No personal task runtime status file yet.");
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  const summary = personal.summary || {};
  setText(
    "personal-task-summary",
    `provider=${personal.provider || "-"} | action=${summary.action || "-"} | dry_run=${summary.dry_run ? "yes" : "no"} | open=${summary.open_count || 0} | overdue=${summary.overdue_count || 0}`
  );

  const tasks = personal.tasks || [];
  if (tasks.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const task of tasks.slice(0, 30)) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      task.title || "-",
      personalTaskDueLabel(task),
      String(task.priority || "-"),
    ]);

    const actionsTd = document.createElement("td");
    const completeBtn = document.createElement("button");
    completeBtn.className = "secondary";
    completeBtn.textContent = "Done";
    completeBtn.addEventListener("click", async () => {
      completeBtn.disabled = true;
      try {
        await completePersonalTask(task);
      } catch (error) {
        showError(error.message);
      } finally {
        completeBtn.disabled = false;
      }
    });
    actionsTd.appendChild(completeBtn);

    const deferBtn = document.createElement("button");
    deferBtn.className = "secondary";
    deferBtn.textContent = "Defer";
    deferBtn.addEventListener("click", async () => {
      deferBtn.disabled = true;
      try {
        await deferPersonalTask(task);
      } catch (error) {
        showError(error.message);
      } finally {
        deferBtn.disabled = false;
      }
    });
    actionsTd.appendChild(deferBtn);
    tr.appendChild(actionsTd);
    body.appendChild(tr);
  }
}

function renderBraindump(snapshot) {
  const body = byId("braindump-body");
  body.innerHTML = "";

  const braindump = snapshot.braindump || {};
  const catalog = braindump.category_catalog || {};
  const categoryList = byId("braindump-category-list");
  const bucketSelect = byId("braindump-review-bucket-select");
  if (categoryList) {
    categoryList.innerHTML = "";
    for (const category of catalog.curated_categories || []) {
      const option = document.createElement("option");
      option.value = category;
      categoryList.appendChild(option);
    }
  }
  if (bucketSelect) {
    const current = bucketSelect.value || "";
    bucketSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "default";
    bucketSelect.appendChild(placeholder);
    for (const bucket of catalog.review_buckets || []) {
      const option = document.createElement("option");
      option.value = bucket;
      option.textContent = bucket;
      bucketSelect.appendChild(option);
    }
    bucketSelect.value = current;
  }

  if (!braindump.available) {
    setText("braindump-status-meta", "No braindump snapshot yet.");
    setText("braindump-bucket-meta", "-");
    setText("braindump-due-meta", "-");
    setText("braindump-category-meta", "-");
    setText("braindump-generated-meta", "-");
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  const statusCounts = braindump.counts_by_status || {};
  const bucketCounts = braindump.counts_by_bucket || {};
  const categoryCounts = braindump.counts_by_category || {};
  const dueItems = braindump.due_items || [];
  const recentItems = braindump.recent_items || [];

  const topCategories = Object.entries(categoryCounts)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 4)
    .map(([name, count]) => `${name}=${count}`);

  setText(
    "braindump-status-meta",
    Object.entries(statusCounts)
      .map(([name, count]) => `${name}=${count}`)
      .join(", ") || "none"
  );
  setText(
    "braindump-bucket-meta",
    Object.entries(bucketCounts)
      .map(([name, count]) => `${name}=${count}`)
      .join(", ") || "none"
  );
  setText("braindump-due-meta", `${braindump.due_count || 0} due for review`);
  setText("braindump-category-meta", topCategories.join(", ") || "none");
  setText("braindump-generated-meta", braindump.generated_at || "-");

  const rows = dueItems.length > 0 ? dueItems : recentItems;
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const item of rows.slice(0, 20)) {
    const tr = document.createElement("tr");

    appendCells(tr, [
      item.short_text || "-",
      item.category || "-",
      item.status || "-",
      item.review_bucket || "-",
      item.next_review_at || item.updated_at || item.captured_at || "-",
    ]);

    const actionsTd = document.createElement("td");
    const addButton = (label, handler) => {
      const btn = document.createElement("button");
      btn.className = "secondary";
      btn.textContent = label;
      btn.style.marginRight = "6px";
      btn.addEventListener("click", handler);
      actionsTd.appendChild(btn);
    };

    if (item.status !== "promoted" && item.status !== "archived") {
      addButton("Park", async () => {
        const bucket = window.prompt("Review bucket", item.review_bucket || "weekly");
        if (bucket === null) {
          return;
        }
        await runBraindumpAction("park", { item_id: item.id, review_bucket: bucket.trim() || item.review_bucket });
      });
      addButton("Task", async () => {
        await runBraindumpAction("promote", { item_id: item.id, target: "task" });
      });
      addButton("Cal", async () => {
        await runBraindumpAction("promote", { item_id: item.id, target: "calendar" });
      });
      addButton("Proj", async () => {
        await runBraindumpAction("promote", { item_id: item.id, target: "project" });
      });
    }

    if (item.status !== "archived") {
      addButton("Archive", async () => {
        if (!window.confirm(`Archive braindump item "${item.short_text || item.id}"?`)) {
          return;
        }
        await runBraindumpAction("archive", { item_id: item.id });
      });
    }

    tr.appendChild(actionsTd);
    body.appendChild(tr);
  }
}

function renderProjects(snapshot) {
  const body = byId("projects-body");
  const projectSelect = byId("task-project-select");

  body.innerHTML = "";
  projectSelect.innerHTML = "";

  const projects = snapshot.workspace.projects || [];
  for (const project of projects) {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = `${project.name} (${project.status})`;
    projectSelect.appendChild(option);
  }

  for (const project of projects) {
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    const nameWrap = document.createElement("div");
    const nameStrong = document.createElement("strong");
    nameStrong.textContent = project.name;
    nameWrap.appendChild(nameStrong);
    if (project.space_key || project.space_entry_command_hint) {
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${project.space_key || "-"} | ${project.space_session_strategy || "-"} | ${project.space_agent_strategy || "-"}${
        project.space_entry_command_hint ? ` | ${project.space_entry_command_hint}` : ""
      }`;
      nameWrap.appendChild(meta);
    }
    nameTd.appendChild(nameWrap);

    const statusTd = document.createElement("td");
    const statusSelect = document.createElement("select");
    for (const status of PROJECT_STATUSES) {
      const option = document.createElement("option");
      option.value = status;
      option.textContent = status;
      option.selected = project.status === status;
      statusSelect.appendChild(option);
    }
    statusTd.appendChild(statusSelect);

    const ownerTd = document.createElement("td");
    ownerTd.textContent = project.owner || "-";

    const tasksTd = document.createElement("td");
    tasksTd.textContent = `${project.task_done}/${project.task_total}`;

    const progressTd = document.createElement("td");
    progressTd.textContent = `${project.progress_pct}%`;

    const actionTd = document.createElement("td");
    const saveBtn = document.createElement("button");
    saveBtn.className = "secondary";
    saveBtn.textContent = "Save";
    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      try {
        await api("/api/projects/update", {
          method: "POST",
          body: {
            project_id: project.id,
            status: statusSelect.value,
          },
        });
        setText("project-status", `Updated ${project.name}`);
        await loadState();
      } catch (error) {
        showError(error.message);
      } finally {
        saveBtn.disabled = false;
      }
    });
    actionTd.appendChild(saveBtn);

    tr.appendChild(nameTd);
    tr.appendChild(statusTd);
    tr.appendChild(ownerTd);
    tr.appendChild(tasksTd);
    tr.appendChild(progressTd);
    tr.appendChild(actionTd);
    body.appendChild(tr);
  }
}

function renderTaskAssignees(snapshot) {
  const container = byId("task-assignee-checkboxes");
  container.innerHTML = "";

  const entities = snapshot.workspace.assignable_entities || [];
  for (const entity of entities) {
    const label = document.createElement("label");
    label.className = "chip";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = entity.id;
    input.className = "chip-check";
    if (entity.id === "pavel") {
      input.checked = true;
    }

    const span = document.createElement("span");
    span.textContent = `${entity.label}${entity.default_lane ? ` (${entity.default_lane})` : ""}`;

    label.appendChild(input);
    label.appendChild(span);
    container.appendChild(label);
  }
}

function renderTaskTemplates(snapshot) {
  const select = byId("task-template-select");
  if (!select) {
    return;
  }

  const templates = (snapshot.workspace || {}).task_templates || [];
  select.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "select template";
  select.appendChild(placeholder);

  for (const template of templates) {
    const option = document.createElement("option");
    option.value = template.name;
    option.textContent = `${template.name} (${template.priority})`;
    select.appendChild(option);
  }
}

function renderSideEffectCatalog(snapshot) {
  const datalist = byId("task-side-effects-list");
  if (!datalist) {
    return;
  }

  datalist.innerHTML = "";
  const catalog = ((snapshot.workspace || {}).side_effect_catalog || []).slice(0, 200);
  for (const effect of catalog) {
    const option = document.createElement("option");
    option.value = effect;
    datalist.appendChild(option);
  }
}

function renderTasks(snapshot) {
  const body = byId("tasks-body");
  body.innerHTML = "";

  const tasks = snapshot.workspace.tasks || [];
  for (const task of tasks) {
    const tr = document.createElement("tr");

    const titleTd = document.createElement("td");
    const titleWrap = document.createElement("div");
    const titleStrong = document.createElement("strong");
    titleStrong.textContent = task.title;
    titleWrap.appendChild(titleStrong);
    if (task.requires_approval || (task.side_effects || []).length) {
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `approval: ${(task.side_effects || []).join(", ") || "manual approval"}`;
      titleWrap.appendChild(meta);
    }
    titleTd.appendChild(titleWrap);

    const projectTd = document.createElement("td");
    projectTd.textContent = task.project_name || "-";

    const assigneesTd = document.createElement("td");
    const assigneesInput = document.createElement("input");
    assigneesInput.type = "text";
    assigneesInput.value = (task.assignees || []).join(", ");
    assigneesInput.style.width = "170px";
    assigneesTd.appendChild(assigneesInput);

    const statusTd = document.createElement("td");
    const statusSelect = document.createElement("select");
    for (const status of TASK_STATUSES) {
      const option = document.createElement("option");
      option.value = status;
      option.textContent = status;
      option.selected = task.status === status;
      statusSelect.appendChild(option);
    }
    statusTd.appendChild(statusSelect);

    const progressTd = document.createElement("td");
    const progressInput = document.createElement("input");
    progressInput.type = "number";
    progressInput.min = "0";
    progressInput.max = "100";
    progressInput.value = Number(task.progress_pct || 0);
    progressInput.style.width = "70px";
    progressTd.appendChild(progressInput);

    const priorityTd = document.createElement("td");
    priorityTd.textContent = task.priority || "medium";

    const dueTd = document.createElement("td");
    dueTd.textContent = task.due_at || "-";

    const actionsTd = document.createElement("td");
    const queueBtn = document.createElement("button");
    queueBtn.className = "secondary";
    queueBtn.textContent = "Queue";

    const saveBtn = document.createElement("button");
    saveBtn.className = "secondary";
    saveBtn.textContent = "Save";

    const doneBtn = document.createElement("button");
    doneBtn.className = "secondary";
    doneBtn.textContent = "Done";

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "secondary";
    deleteBtn.textContent = "Delete";

    const projectBtn = document.createElement("button");
    projectBtn.className = "secondary";
    projectBtn.textContent = "Project";

    const moveBtn = document.createElement("button");
    moveBtn.className = "secondary";
    moveBtn.textContent = "Move";

    const runUpdate = async (payload) => {
      await api("/api/tasks/update", {
        method: "POST",
        body: {
          task_id: task.id,
          ...payload,
        },
      });
      await loadState();
    };

    queueBtn.addEventListener("click", async () => {
      queueBtn.disabled = true;
      try {
        const assignee = assigneesInput.value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)[0];
        const result = await api("/api/tasks/dispatch", {
          method: "POST",
          body: {
            task_id: task.id,
            assignee: assignee || undefined,
            requested_by: "pavel",
          },
        });
        if (result.result && result.result.requires_approval) {
          setText("task-create-status", "Dispatch blocked pending approval.");
        } else {
          setText("task-create-status", "Task queued.");
        }
        await loadState();
      } catch (error) {
        showError(error.message);
      } finally {
        queueBtn.disabled = false;
      }
    });

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      try {
        await runUpdate({
          status: statusSelect.value,
          assignees: assigneesInput.value
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          progress_pct: Number(progressInput.value || 0),
        });
      } catch (error) {
        showError(error.message);
      } finally {
        saveBtn.disabled = false;
      }
    });

    doneBtn.addEventListener("click", async () => {
      doneBtn.disabled = true;
      try {
        await runUpdate({ status: "done", progress_pct: 100 });
      } catch (error) {
        showError(error.message);
      } finally {
        doneBtn.disabled = false;
      }
    });

    deleteBtn.addEventListener("click", async () => {
      deleteBtn.disabled = true;
      try {
        await api("/api/tasks/delete", { method: "POST", body: { task_id: task.id } });
        await loadState();
      } catch (error) {
        showError(error.message);
      } finally {
        deleteBtn.disabled = false;
      }
    });

    projectBtn.addEventListener("click", async () => {
      projectBtn.disabled = true;
      try {
        await promoteTaskToProject(task);
      } catch (error) {
        showError(error.message);
      } finally {
        projectBtn.disabled = false;
      }
    });

    moveBtn.addEventListener("click", async () => {
      moveBtn.disabled = true;
      try {
        const project = promptForProjectSelection(task.project_id || "");
        if (!project) {
          return;
        }
        const result = await api("/api/tasks/move_to_project_space", {
          method: "POST",
          body: {
            task_id: task.id,
            project_id: project.id,
          },
        });
        setText(
          "task-create-status",
          `Task moved to ${result.result.project.name} (${result.result.space.key}).`
        );
        await loadState();
      } catch (error) {
        showError(error.message);
      } finally {
        moveBtn.disabled = false;
      }
    });

    actionsTd.appendChild(queueBtn);
    actionsTd.appendChild(saveBtn);
    actionsTd.appendChild(doneBtn);
    actionsTd.appendChild(moveBtn);
    actionsTd.appendChild(projectBtn);
    actionsTd.appendChild(deleteBtn);

    tr.appendChild(titleTd);
    tr.appendChild(projectTd);
    tr.appendChild(assigneesTd);
    tr.appendChild(statusTd);
    tr.appendChild(progressTd);
    tr.appendChild(priorityTd);
    tr.appendChild(dueTd);
    tr.appendChild(actionsTd);

    body.appendChild(tr);
  }
}

function renderApprovals(snapshot) {
  const body = byId("approvals-body");
  body.innerHTML = "";

  const approvals = (snapshot.workspace || {}).approvals || [];
  if (approvals.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const approval of approvals.slice(0, 40)) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      approval.requested_at || "-",
      approval.task_title || approval.target || "-",
      approval.reason || "-",
      approval.status || "-",
    ]);

    const decisionTd = document.createElement("td");
    if (approval.status === "pending") {
      const approveBtn = document.createElement("button");
      approveBtn.className = "secondary";
      approveBtn.textContent = "Approve";
      approveBtn.addEventListener("click", async () => {
        approveBtn.disabled = true;
        try {
          await api("/api/approvals/decision", {
            method: "POST",
            body: {
              approval_id: approval.id,
              decision: "approved",
              decided_by: "pavel",
            },
          });
          await loadState();
        } catch (error) {
          showError(error.message);
        } finally {
          approveBtn.disabled = false;
        }
      });

      const rejectBtn = document.createElement("button");
      rejectBtn.className = "secondary";
      rejectBtn.textContent = "Reject";
      rejectBtn.addEventListener("click", async () => {
        rejectBtn.disabled = true;
        try {
          const note = window.prompt("Optional rejection note:", "") || "";
          await api("/api/approvals/decision", {
            method: "POST",
            body: {
              approval_id: approval.id,
              decision: "rejected",
              decision_note: note,
              decided_by: "pavel",
            },
          });
          await loadState();
        } catch (error) {
          showError(error.message);
        } finally {
          rejectBtn.disabled = false;
        }
      });

      decisionTd.appendChild(approveBtn);
      decisionTd.appendChild(rejectBtn);
    } else {
      decisionTd.textContent = `${approval.status} by ${approval.decided_by || "-"}`;
    }

    tr.appendChild(decisionTd);
    body.appendChild(tr);
  }
}

function renderRuns(snapshot) {
  const body = byId("runs-body");
  body.innerHTML = "";

  const runs = (snapshot.workspace || {}).runs || [];
  if (runs.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["none", "-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  for (const run of runs.slice(0, 40)) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      run.queued_at || "-",
      run.task_title || run.task_id || "-",
      run.assignee || "-",
      run.status || "-",
      run.updated_at || "-",
    ]);

    const controlsTd = document.createElement("td");
    const postRunUpdate = async (payload) => {
      await api("/api/runs/update", {
        method: "POST",
        body: {
          run_id: run.id,
          actor: "pavel",
          ...payload,
        },
      });
      await loadState();
    };

    if (run.status === "queued") {
      const startBtn = document.createElement("button");
      startBtn.className = "secondary";
      startBtn.textContent = "Start";
      startBtn.addEventListener("click", async () => {
        startBtn.disabled = true;
        try {
          await postRunUpdate({ status: "running", log_message: "Run started from dashboard" });
        } catch (error) {
          showError(error.message);
        } finally {
          startBtn.disabled = false;
        }
      });
      controlsTd.appendChild(startBtn);
    } else if (run.status === "running") {
      const successBtn = document.createElement("button");
      successBtn.className = "secondary";
      successBtn.textContent = "Succeed";
      successBtn.addEventListener("click", async () => {
        successBtn.disabled = true;
        try {
          const summary = window.prompt("Output summary:", "") || "";
          await postRunUpdate({ status: "succeeded", output_summary: summary, log_message: "Run succeeded" });
        } catch (error) {
          showError(error.message);
        } finally {
          successBtn.disabled = false;
        }
      });

      const failBtn = document.createElement("button");
      failBtn.className = "secondary";
      failBtn.textContent = "Fail";
      failBtn.addEventListener("click", async () => {
        failBtn.disabled = true;
        try {
          const message = window.prompt("Failure reason:", "run failed") || "run failed";
          await postRunUpdate({ status: "failed", error: message, log_message: "Run failed" });
        } catch (error) {
          showError(error.message);
        } finally {
          failBtn.disabled = false;
        }
      });

      controlsTd.appendChild(successBtn);
      controlsTd.appendChild(failBtn);
    } else if (RUN_TERMINAL_STATUSES.includes(run.status)) {
      controlsTd.textContent = run.output_summary || run.error || "-";
    } else {
      controlsTd.textContent = "-";
    }

    tr.appendChild(controlsTd);
    body.appendChild(tr);
  }
}

function renderUsage(snapshot) {
  const laneBody = byId("usage-lane-body");
  const recentBody = byId("recent-calls-body");
  laneBody.innerHTML = "";
  recentBody.innerHTML = "";

  const local = snapshot.telemetry.local || {};
  const rows = local.by_lane || [];

  if (!rows.length) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "0", "0", "0", "0", "0"]);
    laneBody.appendChild(tr);
  } else {
    for (const row of rows) {
      const tr = document.createElement("tr");
      appendCells(tr, [
        row.lane,
        formatInt(row.calls),
        formatInt(row.total_tokens),
        formatInt(row.errors),
        formatInt(row.fallbacks),
        formatInt(row.avg_latency_ms),
      ]);
      laneBody.appendChild(tr);
    }
  }

  for (const call of local.recent_calls || []) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      call.ts || "-",
      call.task_id || "-",
      call.lane || "-",
      call.model || "-",
      call.status || "-",
      formatInt(call.tokens || 0),
      formatUsd(call.estimated_cost_usd || 0),
    ]);
    recentBody.appendChild(tr);
  }

  if (!local.recent_calls || local.recent_calls.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-", "0", "$0.0000"]);
    recentBody.appendChild(tr);
  }

  setText("usage-source", `source: ${local.source || "not available"}`);
}

function firstField(row, keys) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key)) {
      return row[key];
    }
  }
  return "-";
}

function renderCodexbar(snapshot) {
  const body = byId("codexbar-body");
  body.innerHTML = "";

  const codexbar = snapshot.telemetry.codexbar || {};
  const cost = codexbar.cost || {};

  if (!cost.enabled) {
    setText("codexbar-status", "Codexbar cost adapter disabled.");
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  if (!cost.available) {
    setText("codexbar-status", `Codexbar unavailable: ${cost.error || "unknown error"}`);
    const tr = document.createElement("tr");
    appendCells(tr, ["-", "-", "-", "-", "-"]);
    body.appendChild(tr);
    return;
  }

  const rows = cost.rows || [];
  setText("codexbar-status", `${rows.length} codexbar rows loaded (${codexbar.provider})`);

  for (const row of rows) {
    const tr = document.createElement("tr");
    appendCells(tr, [
      String(firstField(row, ["Provider", "provider"])),
      String(firstField(row, ["Model", "model"])),
      String(firstField(row, ["Input Tokens", "input_tokens", "input"])),
      String(firstField(row, ["Output Tokens", "output_tokens", "output"])),
      String(firstField(row, ["Total Cost (USD)", "total_cost_usd", "cost_usd"])),
    ]);
    body.appendChild(tr);
  }

  if (rows.length === 0) {
    const tr = document.createElement("tr");
    appendCells(tr, ["no data", "-", "-", "-", "-"]);
    body.appendChild(tr);
  }
}

function renderReports(snapshot) {
  const telemetry = snapshot.telemetry || {};
  const reportState = telemetry.report_markdown_present ? "model report: present" : "model report: missing";
  const opsState = telemetry.ops_snapshot_present ? "ops snapshot: present" : "ops snapshot: missing";
  setText("report-files", `${reportState} | ${opsState}`);
}

async function applyProfiles() {
  const integrationProfile = byId("integration-profile-select").value;
  const memoryProfile = byId("memory-profile-select").value;

  const result = await api("/api/profiles", {
    method: "POST",
    body: {
      integrations_profile: integrationProfile,
      memory_profile: memoryProfile,
    },
  });

  setText("profile-status", result.result.message || "profiles updated");
  await loadState();
}

async function saveDashboardSettings() {
  const provider = byId("codexbar-provider-select").value;
  const routingMode = byId("routing-mode-select").value;
  const refresh = Number(byId("refresh-seconds-input").value || 20);
  const authRequired = byId("auth-required-toggle").checked;
  const authEnvKey = byId("auth-env-key-input").value.trim() || "OPENCLAW_DASHBOARD_TOKEN";
  const authAllowGeneratedToken = byId("auth-allow-generated-toggle").checked;

  await api("/api/dashboard/settings", {
    method: "POST",
    body: {
      codexbar_provider: provider,
      routing_mode: routingMode || undefined,
      auto_refresh_seconds: refresh,
      auth_require_token: authRequired,
      auth_token_env_key: authEnvKey,
      auth_allow_generated_token: authAllowGeneratedToken,
    },
  });

  setText("adapter-status", `Settings updated. Routing mode: ${routingMode || "-"}.`);
  await loadState();
}

async function runProviderSmoke(live) {
  const endpoint = "/api/provider_smoke/run";
  const result = await api(endpoint, {
    method: "POST",
    body: { live },
  });
  const summary = ((result || {}).result || {}).summary || {};
  setText(
    "provider-health-summary",
    `${summary.configured_count || 0}/${summary.total_providers || 0} configured | ${summary.locally_usable_count || 0} locally usable | ${summary.live_ok_count || 0} live ok`
  );
  await loadState();
}

function selectedAssigneesForCreate() {
  const container = byId("task-assignee-checkboxes");
  const checks = Array.from(container.querySelectorAll("input[type='checkbox']"));
  return checks.filter((item) => item.checked).map((item) => item.value);
}

async function createProject() {
  const name = byId("project-name-input").value.trim();
  if (!name) {
    showError("Project name is required.");
    return;
  }

  const payload = {
    name,
    owner: byId("project-owner-input").value.trim() || "pavel",
    status: "active",
  };
  const targetDate = byId("project-target-date-input").value;
  const description = byId("project-description-input").value.trim();
  if (targetDate) {
    payload.target_date = targetDate;
  }
  if (description) {
    payload.description = description;
  }

  const result = await api("/api/projects/create", {
    method: "POST",
    body: payload,
  });

  byId("project-name-input").value = "";
  byId("project-description-input").value = "";
  setText("project-status", `Project created. Space: space-${result.project.id}`);
  await loadState();
}

async function promoteTaskToProject(task) {
  const name = window.prompt("New project name", task.title || "Project");
  if (name === null) {
    return;
  }
  const cleanName = name.trim();
  if (!cleanName) {
    throw new Error("project name is required");
  }

  const description = window.prompt("Project description", task.notes || task.title || "");
  if (description === null) {
    return;
  }

  const result = await api("/api/projects/promote_task", {
    method: "POST",
    body: {
      task_id: task.id,
      name: cleanName,
      description: description.trim() || undefined,
    },
  });
  setText(
    "task-create-status",
    `Task promoted to project ${result.result.project.name} with space ${result.result.space.key}.`
  );
  await loadState();
}

async function createTask() {
  const title = byId("task-title-input").value.trim();
  if (!title) {
    showError("Task title is required.");
    return;
  }

  const assignees = selectedAssigneesForCreate();
  if (assignees.length === 0) {
    showError("Select at least one assignee.");
    return;
  }

  const dueRaw = byId("task-due-input").value;
  const dueAt = dueRaw ? new Date(dueRaw).toISOString() : null;
  const sideEffects = parseCommaList(byId("task-side-effects-input").value);
  const requiresApproval = byId("task-requires-approval-toggle").checked;
  const payload = {
    title,
    project_id: byId("task-project-select").value || undefined,
    priority: byId("task-priority-select").value,
    notes: byId("task-notes-input").value.trim() || undefined,
    assignees,
    status: "todo",
    requires_approval: requiresApproval,
  };
  if (dueAt) {
    payload.due_at = dueAt;
  }
  if (sideEffects.length) {
    payload.side_effects = sideEffects;
  }

  await api("/api/tasks/create", {
    method: "POST",
    body: payload,
  });

  byId("task-title-input").value = "";
  byId("task-notes-input").value = "";
  byId("task-due-input").value = "";
  byId("task-side-effects-input").value = "";
  byId("task-requires-approval-toggle").checked = false;
  setText("task-create-status", "Task created and assigned.");
  await loadState();
}

async function createTaskFromTemplate() {
  const templateName = byId("task-template-select").value;
  if (!templateName) {
    showError("Select a template first.");
    return;
  }

  const assignees = selectedAssigneesForCreate();
  const dueRaw = byId("task-due-input").value;
  const dueAt = dueRaw ? new Date(dueRaw).toISOString() : null;
  const sideEffects = parseCommaList(byId("task-side-effects-input").value);
  const requiresApproval = byId("task-requires-approval-toggle").checked;

  const payload = {
    template_name: templateName,
    requires_approval: requiresApproval,
  };
  const title = byId("task-title-input").value.trim();
  const projectId = byId("task-project-select").value;
  const priority = byId("task-priority-select").value;
  const notes = byId("task-notes-input").value.trim();
  if (title) {
    payload.title = title;
  }
  if (projectId) {
    payload.project_id = projectId;
  }
  if (priority) {
    payload.priority = priority;
  }
  if (dueAt) {
    payload.due_at = dueAt;
  }
  if (notes) {
    payload.notes = notes;
  }
  if (assignees.length) {
    payload.assignees = assignees;
  }
  if (sideEffects.length) {
    payload.side_effects = sideEffects;
  }

  const result = await api("/api/tasks/create_from_template", {
    method: "POST",
    body: payload,
  });

  byId("task-title-input").value = "";
  byId("task-notes-input").value = "";
  byId("task-due-input").value = "";
  byId("task-side-effects-input").value = "";
  byId("task-requires-approval-toggle").checked = false;
  setText("task-create-status", `Template task created: ${result.result.task.title}`);
  await loadState();
}

async function downloadFile(path, filename) {
  const response = await fetch(path, { method: "GET" });
  if (response.status === 401) {
    window.location.href = "/login.html";
    throw new Error("unauthorized");
  }
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function exportWeeklyMarkdown() {
  const date = new Date().toISOString().slice(0, 10);
  await downloadFile("/api/exports/weekly.md?days=7", `openclaw-weekly-${date}.md`);
  setText("export-status", "Weekly markdown exported.");
}

async function exportTasksCsv() {
  const date = new Date().toISOString().slice(0, 10);
  await downloadFile("/api/exports/tasks.csv", `openclaw-tasks-${date}.csv`);
  setText("export-status", "Tasks CSV exported.");
}

async function logout() {
  await api("/api/auth/logout", { method: "POST", body: {} });
  window.location.href = "/login.html";
}

async function runBraindumpAction(action, body) {
  const endpoint = `/api/braindump/${action}`;
  await api(endpoint, { method: "POST", body });
  setText("braindump-capture-status", `Braindump ${action} applied.`);
  await loadState();
}

async function captureBraindump() {
  const text = byId("braindump-capture-input").value.trim();
  const category = byId("braindump-category-input").value.trim();
  const tags = parseCommaList(byId("braindump-tags-input").value || "");
  const reviewBucket = byId("braindump-review-bucket-select").value || "";

  if (!text) {
    throw new Error("braindump capture text is required");
  }

  const routeResponse = await api("/api/spaces/route_text", {
    method: "POST",
    body: { text },
  });
  const route = ((routeResponse || {}).result || {}).route || null;
  if (route && route.kind === "project" && route.matched && !route.resolved) {
    throw new Error(`Project space not found: ${route.space_key}`);
  }
  const routedText =
    route && route.kind === "project" && route.resolved && route.stripped_text ? route.stripped_text : text;
  const routeNote = route && route.kind === "project" && route.resolved ? `space=${route.space_key}` : undefined;

  if (category) {
    await api("/api/braindump/create", {
      method: "POST",
      body: {
        category,
        text: routedText,
        tags,
        review_bucket: reviewBucket || undefined,
        notes: routeNote,
        source: "web_dashboard",
      },
    });
  } else {
    await api("/api/braindump/capture", {
      method: "POST",
      body: {
        text,
        source: "web_dashboard",
      },
    });
  }

  byId("braindump-capture-input").value = "";
  byId("braindump-category-input").value = "";
  byId("braindump-tags-input").value = "";
  byId("braindump-review-bucket-select").value = "";
  setText(
    "braindump-capture-status",
    route && route.kind === "project" && route.resolved
      ? `Braindump item captured in ${route.space_key}.`
      : "Braindump item captured."
  );
  await loadState();
}

function configureAutoRefresh(snapshot) {
  const refreshSeconds = Number(
    (((snapshot.dashboard || {}).dashboard || {}).ui || {}).auto_refresh_seconds || 20
  );

  if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
    state.refreshTimer = null;
  }

  state.refreshTimer = setInterval(() => {
    if (!state.loading) {
      loadState();
    }
  }, Math.max(5000, refreshSeconds * 1000));
}

async function loadState() {
  state.loading = true;
  showError("");

  try {
    const snapshot = await api("/api/state");
    state.snapshot = snapshot;

    renderProfiles(snapshot);
    renderPresets(snapshot);
    renderAdapters(snapshot);
    renderMetrics(snapshot);
    renderIntegrationLists(snapshot);
    renderProviderHealth(snapshot);
    renderAgentRuntime(snapshot);
    renderReminders(snapshot);
    renderTodoQueue(snapshot);
    renderGmailInbox(snapshot);
    renderCalendarRuntime(snapshot);
    renderDriveWorkspace(snapshot);
    renderCalendarCandidates(snapshot);
    renderPersonalTasks(snapshot);
    renderBraindump(snapshot);
    renderProjects(snapshot);
    renderTaskAssignees(snapshot);
    renderTaskTemplates(snapshot);
    renderSideEffectCatalog(snapshot);
    renderTasks(snapshot);
    renderApprovals(snapshot);
    renderRuns(snapshot);
    renderUsage(snapshot);
    renderCodexbar(snapshot);
    renderReports(snapshot);

    configureAutoRefresh(snapshot);
  } catch (error) {
    setHealth(false, "offline");
    showError(error.message);
  } finally {
    state.loading = false;
  }
}

function bindEvents() {
  byId("refresh-button").addEventListener("click", () => loadState());

  byId("apply-profiles-button").addEventListener("click", async () => {
    try {
      await applyProfiles();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("save-dashboard-settings").addEventListener("click", async () => {
    try {
      await saveDashboardSettings();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("provider-smoke-local-button").addEventListener("click", async () => {
    try {
      await runProviderSmoke(false);
    } catch (error) {
      showError(error.message);
    }
  });

  byId("provider-smoke-live-button").addEventListener("click", async () => {
    try {
      await runProviderSmoke(true);
    } catch (error) {
      showError(error.message);
    }
  });

  byId("capture-braindump-button").addEventListener("click", async () => {
    try {
      await captureBraindump();
    } catch (error) {
      showError(error.message);
    }
  });
  byId("braindump-capture-input").addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    try {
      await captureBraindump();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("calendar-apply-approved-button").addEventListener("click", async () => {
    const button = byId("calendar-apply-approved-button");
    button.disabled = true;
    try {
      await applyApprovedCalendarCandidates();
    } catch (error) {
      showError(error.message);
    } finally {
      button.disabled = false;
    }
  });

  byId("create-personal-task-button").addEventListener("click", async () => {
    try {
      await createPersonalTask();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("sync-personal-task-button").addEventListener("click", async () => {
    try {
      await syncPersonalTasks();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("create-project-button").addEventListener("click", async () => {
    try {
      await createProject();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("create-task-button").addEventListener("click", async () => {
    try {
      await createTask();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("create-template-task-button").addEventListener("click", async () => {
    try {
      await createTaskFromTemplate();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("export-weekly-md-button").addEventListener("click", async () => {
    try {
      await exportWeeklyMarkdown();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("export-tasks-csv-button").addEventListener("click", async () => {
    try {
      await exportTasksCsv();
    } catch (error) {
      showError(error.message);
    }
  });

  byId("logout-button").addEventListener("click", async () => {
    try {
      await logout();
    } catch (error) {
      showError(error.message);
    }
  });
}

bindEvents();
loadState();
