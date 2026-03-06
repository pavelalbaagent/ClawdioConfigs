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
    nameTd.textContent = project.name;

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

    actionsTd.appendChild(queueBtn);
    actionsTd.appendChild(saveBtn);
    actionsTd.appendChild(doneBtn);
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

  await api("/api/projects/create", {
    method: "POST",
    body: payload,
  });

  byId("project-name-input").value = "";
  byId("project-description-input").value = "";
  setText("project-status", "Project created.");
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
    renderReminders(snapshot);
    renderTodoQueue(snapshot);
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
