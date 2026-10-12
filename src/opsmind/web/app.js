"use strict";
const $ = (id) => document.getElementById(id);
let current = null;
let busy = false;
const states = {
  running: "处理中",
  waiting_confirmation: "等待确认",
  completed: "已完成",
  failed: "处理失败",
  rejected: "已拒绝",
};
const names = {
  equipment_no: "设备编号",
  title: "标题",
  description: "故障描述",
  priority: "优先级",
  category: "类别",
  assigned_to: "处理人 ID",
  status: "状态",
  diagnosis: "诊断",
  ticket_no: "工单编号",
};
const tools = {
  get_equipment: "查询设备",
  get_maintenance_history: "查询维修记录",
  get_ticket_history: "查询工单",
  search_knowledge: "检索知识库",
  create_ticket: "创建工单",
  update_ticket: "修改工单",
};
function error(message) {
  $("error").hidden = !message;
  $("error").textContent = message;
}
function lock(value, message = "") {
  busy = value;
  document.querySelectorAll("button").forEach((b) => (b.disabled = value));
  $("notice").textContent = message;
  $("output")?.setAttribute("aria-busy", String(value));
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error("服务器返回无法识别的内容，请检查后端日志。");
  }
  if (!response.ok) {
    const code = body.error?.code;
    throw new Error(
      code
        ? `请求未完成：${code}。请检查任务状态或后端配置。`
        : `请求未完成（HTTP ${response.status}），请核对输入后再试。`,
    );
  }
  return body;
}
function pairs(target, entries) {
  const container = $(target);
  container.replaceChildren();
  for (const [key, value] of entries) {
    const dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent =
      typeof value === "object"
        ? JSON.stringify(value, null, 2)
        : String(value ?? "未知");
    container.append(dt, dd);
  }
}
function render(run) {
  current = run;
  $("empty").hidden = true;
  $("run").hidden = false;
  $("current-id").textContent = run.id;
  $("run-id").value = run.id;
  $("status").textContent = states[run.status] || run.status;
  const answer =
    run.result ||
    (run.status === "failed"
      ? `本次处理未完成：${run.error_code || "未知错误"}。可查看执行记录。`
      : run.status === "rejected"
        ? "已拒绝本次操作，未批准该写入。"
        : run.status === "running"
          ? "任务尚未结束，可刷新状态或恢复执行。"
          : "已生成操作提议，请核对下方内容。");
  renderMarkdown($("answer"), answer);
  const action = run.pending_action;
  $("approval").hidden = run.status !== "waiting_confirmation" || !action;
  $("resume").hidden = run.status !== "running";
  if (action) {
    $("action-name").textContent = tools[action.tool] || action.tool;
    pairs(
      "arguments",
      Object.entries(action.arguments).map(([k, v]) => [names[k] || k, v]),
    );
    $("expires").textContent =
      `确认有效期至 ${new Date(action.expires_at).toLocaleString("zh-CN")}`;
  }
  try {
    sessionStorage.setItem("opsmind-run", run.id);
  } catch {}
}
async function trace() {
  const data = await api(`/api/v1/agent/runs/${current.id}/trace`);
  const m = data.metrics;
  pairs("metrics", [
    ["模型调用", m.model_calls],
    ["工具调用", m.tool_calls],
    [
      "已记录处理耗时",
      m.observed_processing_ms == null
        ? "未知"
        : `${m.observed_processing_ms} ms`,
    ],
    ["Token 总量", m.token_usage?.total_tokens ?? "未知"],
    ["已结束审批等待", `${m.approval_wait_ms} ms`],
  ]);
  $("events").replaceChildren();
  for (const e of data.events) {
    const li = document.createElement("li");
    li.textContent = [
      e.at ? new Date(e.at).toLocaleTimeString("zh-CN") : "",
      e.kind,
      tools[e.tool] || e.tool,
      e.code,
      e.duration_ms != null ? `${e.duration_ms} ms` : "",
    ]
      .filter(Boolean)
      .join(" · ");
    $("events").append(li);
  }
  $("sources").replaceChildren();
  const seen = new Set();
  for (const e of data.events.filter((e) => e.kind === "retrieval")) {
    for (const h of e.items || []) {
      if (seen.has(h.citation)) continue;
      seen.add(h.citation);
      const li = document.createElement("li");
      li.textContent = `[${h.citation}] ${h.source} / ${h.heading} · 版本 ${h.version}`;
      $("sources").append(li);
    }
  }
  if (!seen.size) {
    const li = document.createElement("li");
    li.textContent = "本次暂无检索来源。没有引用不代表信息已得到资料验证。";
    $("sources").append(li);
  }
}
async function perform(work, message) {
  if (busy) return;
  error("");
  lock(true, message);
  try {
    await work();
  } catch (e) {
    error(
      e instanceof TypeError
        ? "连接中断，服务器可能仍在处理。不要重复提交；已有运行编号时请查询状态。"
        : e.message,
    );
  } finally {
    lock(false);
  }
}
async function show(run) {
  render(run);
  $("sources").replaceChildren();
  $("events").replaceChildren();
  $("metrics").replaceChildren();
  try {
    await trace();
  } catch (e) {
    error(`任务状态已获取，但执行记录加载失败。${e.message}`);
  }
}
$("task-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const message = $("message").value.trim();
  if (!message) return;
  perform(async () => {
    await show(
      await api("/api/v1/agent/runs", {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    );
  }, "正在查询与分析，请保留页面。模型处理可能需要几分钟。");
});
$("load-form").addEventListener("submit", (e) => {
  e.preventDefault();
  perform(
    async () =>
      show(await api(`/api/v1/agent/runs/${$("run-id").value.trim()}`)),
    "正在查询任务状态…",
  );
});
$("refresh").addEventListener("click", () =>
  perform(
    async () => show(await api(`/api/v1/agent/runs/${current.id}`)),
    "正在刷新…",
  ),
);
$("resume").addEventListener("click", () =>
  perform(
    async () =>
      show(
        await api(`/api/v1/agent/runs/${current.id}/resume`, {
          method: "POST",
        }),
      ),
    "正在恢复执行，可能继续调用模型…",
  ),
);
for (const [id, approved] of [
  ["approve", true],
  ["reject", false],
]) {
  $(id).addEventListener("click", () => {
    const run = current;
    if (!run?.pending_action) return;
    perform(
      async () =>
        show(
          await api(`/api/v1/agent/runs/${run.id}/decisions`, {
            method: "POST",
            body: JSON.stringify({
              action_id: run.pending_action.action_id,
              approved,
            }),
          }),
        ),
      approved ? "正在执行已确认的操作，请勿重复点击…" : "正在拒绝操作…",
    );
  });
}
document.querySelectorAll("[data-example]").forEach((b) =>
  b.addEventListener("click", () => {
    $("message").value = b.dataset.example;
    $("message").focus();
  }),
);
try {
  const saved = sessionStorage.getItem("opsmind-run");
  if (/^[a-f0-9]{32}$/.test(saved)) $("run-id").value = saved;
} catch {}
api("/health")
  .then(() => ($("health").textContent = "后端在线 · 数据库待查询"))
  .catch(() => ($("health").textContent = "后端未连接"));
