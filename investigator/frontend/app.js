const questionInput = document.querySelector("#question");
const runButton = document.querySelector("#run");
const followButton = document.querySelector("#follow-up");
const requestError = document.querySelector("#request-error");
const savedList = document.querySelector("#saved-list");
const downloadLink = document.querySelector("#download");
const result = document.querySelector("#result");
const technical = document.querySelector("#technical");
const savedInvestigations = document.querySelector("#saved-investigations");

let running = false;
let selectedId = "";
let selectedDatabaseRecorded = false;

runButton.addEventListener("click", () => {
  submitLive("/api/investigations", {
    question: questionInput.value,
    dataset: selectedDataset(),
  });
});

followButton.addEventListener("click", () => {
  if (!selectedId) {
    showError("Load a saved investigation before asking a follow-up.");
    return;
  }
  const body = { question: questionInput.value };
  if (!selectedDatabaseRecorded) {
    body.dataset = selectedDataset();
  }
  submitLive(`/api/investigations/${encodeURIComponent(selectedId)}/follow-ups`, body);
});

savedList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button || running) {
    return;
  }
  const investigationId = button.dataset.id;
  if (investigationId === selectedId && !result.hidden) {
    result.open = !result.open;
    if (result.open) {
      result.scrollIntoView({ block: "start" });
    }
    return;
  }
  loadReport(investigationId);
});

result.addEventListener("toggle", () => {
  if (result.hidden || !selectedId) {
    return;
  }
  savedInvestigations.open = !result.open;
  markOpenReport();
});

downloadLink.addEventListener("click", (event) => {
  if (!selectedId) {
    event.preventDefault();
  }
});

refreshSavedList();

async function refreshSavedList() {
  const payload = await requestJson("/api/reports");
  if (!payload) {
    return;
  }
  savedList.replaceChildren();
  const reports = sortReports(payload.reports || []);
  if (!reports.length) {
    savedList.append(paragraph("No saved investigations yet."));
    return;
  }
  for (const report of reports) {
    savedList.append(savedItem(report));
  }
  markOpenReport();
}

async function loadReport(investigationId) {
  if (!investigationId || running) {
    return;
  }
  const payload = await requestJson(`/api/reports/${encodeURIComponent(investigationId)}`);
  if (!payload) {
    return;
  }
  showReport(payload);
  markOpenReport();
}

async function submitLive(url, body) {
  if (running) {
    return;
  }
  setBusy(true);
  showError("");
  const payload = await requestJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  setBusy(false);
  if (!payload) {
    return;
  }
  showReport(payload);
  await refreshSavedList();
}

async function requestJson(url, options) {
  try {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) {
      showError(errorText(payload));
      return null;
    }
    showError("");
    return payload;
  } catch (error) {
    showError(error instanceof Error ? error.message : "The request failed.");
    return null;
  }
}

function showReport(payload) {
  const report = payload.report;
  selectedId = report.investigation_id || "";
  const database = report.database || {};
  selectedDatabaseRecorded = Boolean(database.path && database.sha256);
  followButton.disabled = running || !selectedId;
  downloadLink.href = selectedId ? `/api/reports/${encodeURIComponent(selectedId)}/download` : "#";
  downloadLink.setAttribute("aria-disabled", selectedId ? "false" : "true");
  technical.open = false;
  for (const nested of technical.querySelectorAll("details")) {
    nested.open = false;
  }
  savedInvestigations.open = false;
  result.hidden = false;
  result.open = true;
  setText("#origin", originText(payload.origin, report.response_source, report.status));
  document.querySelector("#origin").className = bannerClass(report.response_source, report.status);
  setText("#result-question", report.question || "");
  const status = document.querySelector("#result-status");
  status.textContent = statusLabel(report.status);
  status.className = `badge ${badgeClass(report.status)}`;
  document.querySelector("#result-follow-up").hidden = !report.parent_investigation_id;
  setText("#result-status-detail", statusLabel(report.status));
  setText("#result-dataset", datasetName(database));
  setText("#result-id", selectedId || "Not recorded");
  setText("#result-verification", report.explanation_verification || "Not recorded");
  setText("#result-reason", failureText(report));
  setText("#result-database", database.path || "Not recorded");
  setText("#result-hash", database.sha256 || "Not recorded");
  setText("#result-explanation", report.explanation || "No explanation was saved.");
  setText("#result-citations", citationText(report));
  setText(
    "#units",
    `${report.amount_units || "Amounts are integer USD cents."} ${report.date_ranges || ""}`.trim(),
  );
  renderEvidence(report);
  renderSummary(report);
  renderAttempts(report);
  renderParent(report.parent_investigation_id);
  result.scrollIntoView({ block: "start" });
  markOpenReport();
}

function originText(origin, responseSource, status) {
  const saved = origin !== "new";
  const mock = responseSource === "mock";
  const failed = status && status !== "complete";
  if (!saved && !mock) {
    return failed ? "New live model response. This run did not complete." : "New live model response.";
  }
  if (!saved && mock) {
    return "New mock response. This was not a live model call.";
  }
  if (mock) {
    return "Saved mock response. It was loaded from disk and was not a live model call.";
  }
  if (failed) {
    return "Saved historical run. It failed, was loaded from disk, and was not regenerated.";
  }
  return "Saved live model response. It was loaded from disk and was not regenerated.";
}

function bannerClass(responseSource, status) {
  if (status && status !== "complete") {
    return "banner banner-error";
  }
  if (responseSource === "mock") {
    return "banner banner-mock";
  }
  return "banner banner-live";
}

function failureText(report) {
  if (report.status === "complete") {
    return "";
  }
  return report.incomplete_reason || "This investigation did not complete. No further reason was saved.";
}

function citationText(report) {
  const cited = report.conclusion_evidence_ids || [];
  const unknown = report.unknown_citations || [];
  const parts = [];
  parts.push(cited.length ? cited.join(", ") : "No evidence IDs were cited.");
  if (unknown.length) {
    parts.push(`Unknown citations: ${unknown.join(", ")}`);
  }
  return parts.join(" ");
}

function renderEvidence(report) {
  const summary = document.querySelector("#evidence-summary");
  summary.replaceChildren();
  const cited = new Set(report.conclusion_evidence_ids || []);
  const items = report.evidence || [];
  const visible = cited.size
    ? items.filter((item) => cited.has(item.evidence_id))
    : items.filter((item) => {
      const status = item.result && item.result.status;
      return status === "ok" || status === "truncated";
    });
  if (!visible.length) {
    summary.append(paragraph("No cited or successful evidence was saved."));
    return;
  }
  const list = document.createElement("ul");
  list.className = "evidence-list";
  for (const item of visible) {
    const row = document.createElement("li");
    const identifier = document.createElement("span");
    identifier.className = "evidence-id";
    identifier.textContent = evidenceLabel(item.evidence_id);
    const purpose = document.createElement("p");
    purpose.className = "evidence-purpose";
    purpose.textContent = item.purpose || "Saved result";
    const resultLine = document.createElement("p");
    resultLine.className = "evidence-result";
    resultLine.textContent = resultSummary(item.result);
    row.append(identifier, purpose, resultLine);
    list.append(row);
  }
  summary.append(list);
}

function resultSummary(queryResult) {
  if (!queryResult) {
    return "No result was saved.";
  }
  if (queryResult.status === "truncated") {
    return `Truncated (${queryResult.truncation_reason || "partial"}). ${rowSummary(queryResult)}`;
  }
  if (queryResult.status === "error") {
    return queryResult.error || "The query failed.";
  }
  if (queryResult.status !== "ok") {
    return queryResult.error || queryResult.status || "No table was returned.";
  }
  return rowSummary(queryResult);
}

function rowSummary(queryResult) {
  const columns = queryResult.columns || [];
  const rows = queryResult.rows || [];
  if (!rows.length) {
    return "No rows returned.";
  }
  if (rows.length === 1 && columns.length === 1 && columns[0].endsWith("_count")) {
    return countPhrase(columns[0], rows[0][0]);
  }
  if (rows.length === 1 && columns.length && columns.length <= 8) {
    return columns.map((column, index) => compactField(column, rows[0][index])).filter(Boolean).join(" · ");
  }
  return `${rows.length} rows.`;
}

function countPhrase(column, value) {
  const stem = column.slice(0, -"_count".length).replaceAll("_", " ");
  const noun = stem.endsWith("s") ? stem : `${stem}s`;
  return `${formatCell(value)} ${noun}`;
}

function compactField(column, value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const cents = column.endsWith("_cents") ? asInteger(value) : null;
  if (cents !== null) {
    return formatCents(cents);
  }
  if (column === "order_id") {
    return `Order ${value}`;
  }
  if (column === "customer_id") {
    return `Customer ${value}`;
  }
  if (column === "refund_id" || column.endsWith("_date")) {
    return String(value);
  }
  return `${column.replaceAll("_", " ")}: ${formatCell(value)}`;
}

function asInteger(value) {
  if (typeof value === "number" && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === "string" && /^-?\d+$/.test(value)) {
    return Number(value);
  }
  return null;
}

function formatCents(cents) {
  const negative = cents < 0;
  return `${negative ? "-" : ""}$${(Math.abs(cents) / 100).toFixed(2)}`;
}

function formatCell(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function renderSummary(report) {
  const summary = document.querySelector("#summary");
  summary.replaceChildren();
  const successful = (report.evidence || []).filter((item) => {
    const status = item.result && item.result.status;
    return status === "ok" || status === "truncated";
  });
  if (!successful.length) {
    summary.append(paragraph("No successful SQL result was saved."));
    return;
  }
  for (const item of successful) {
    summary.append(paragraph(`${item.evidence_id || "Unlabeled result"} — ${item.purpose || ""}`));
    const queryResult = item.result || {};
    if (queryResult.status === "truncated") {
      summary.append(paragraph(`Truncated result (${queryResult.truncation_reason || "partial"}). Rows below are incomplete.`));
    }
    summary.append(resultTable(queryResult));
  }
}

function renderAttempts(report) {
  const attempts = document.querySelector("#attempts");
  attempts.replaceChildren();
  const rows = report.sql_attempts || [];
  const rejected = report.rejected_tool_calls || [];
  if (!rows.length && !rejected.length) {
    attempts.append(paragraph("No SQL attempt was saved."));
    return;
  }
  for (const attempt of rows) {
    const block = document.createElement("div");
    block.className = "attempt";
    block.append(paragraph(`${attempt.evidence_id || "Not executed"} — ${attempt.status || "unknown"} — ${attempt.purpose || ""}`));
    const sql = document.createElement("pre");
    sql.textContent = attempt.sql || "";
    block.append(sql);
    if (attempt.error) {
      block.append(paragraph(attempt.error));
    }
    const queryResult = attempt.result || {};
    if (queryResult.truncated) {
      block.append(paragraph(`Truncated (${queryResult.truncation_reason || "partial"}).`));
    }
    if (queryResult.columns) {
      block.append(resultTable(queryResult));
    }
    attempts.append(block);
  }
  for (const rejectedCall of rejected) {
    const block = document.createElement("div");
    block.className = "attempt";
    block.append(paragraph(`Rejected tool call — ${rejectedCall.error || "invalid"}`));
    const sql = document.createElement("pre");
    sql.textContent = rejectedCall.arguments || "";
    block.append(sql);
    attempts.append(block);
  }
}

async function renderParent(parentId) {
  const parent = document.querySelector("#parent");
  parent.replaceChildren();
  if (!parentId) {
    parent.append(paragraph("This investigation has no parent."));
    return;
  }
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(parentId)}`);
    const payload = await response.json();
    if (!response.ok) {
      parent.append(paragraph(errorText(payload)));
      return;
    }
    const report = payload.report;
    parent.append(paragraph(`Parent ${report.investigation_id || parentId}`));
    parent.append(paragraph(`Question: ${report.question || ""}`));
    parent.append(paragraph(`Status: ${statusLabel(report.status)}`));
    const database = report.database || {};
    parent.append(paragraph(`Database: ${database.path || "Not recorded"}`));
    parent.append(paragraph(`SHA-256: ${database.sha256 || "Not recorded"}`));
    parent.append(paragraph(report.explanation || "No parent explanation was saved."));
    if (report.status !== "complete" && report.incomplete_reason) {
      parent.append(paragraph(report.incomplete_reason));
    }
  } catch (error) {
    parent.append(paragraph(error instanceof Error ? error.message : "The parent report could not be loaded."));
  }
}

function resultTable(queryResult) {
  const columns = queryResult.columns || [];
  const rows = queryResult.rows || [];
  if (!columns.length && !rows.length) {
    return paragraph(queryResult.status === "ok" ? "The query returned no rows." : "No table was returned.");
  }
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = String(column);
    head.append(cell);
  }
  table.append(head);
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = Math.max(columns.length, 1);
    cell.textContent = "No rows returned.";
    row.append(cell);
    table.append(row);
    return table;
  }
  for (const values of rows) {
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = formatCell(value);
      row.append(cell);
    }
    table.append(row);
  }
  return table;
}

function savedItem(report) {
  const item = document.createElement("article");
  item.className = "saved-item";
  item.dataset.id = report.investigation_id || "";
  const copy = document.createElement("div");
  const badges = document.createElement("div");
  badges.className = "badge-row";
  const badge = document.createElement("span");
  badge.className = `badge ${badgeClass(report.status)}`;
  badge.textContent = statusLabel(report.status);
  badges.append(badge);
  if (report.parent_investigation_id) {
    const follow = document.createElement("span");
    follow.className = "badge badge-follow";
    follow.textContent = "Follow-up";
    badges.append(follow);
  }
  const question = document.createElement("p");
  question.className = "saved-question";
  question.textContent = report.question || "No question saved";
  const meta = document.createElement("p");
  meta.className = "saved-meta";
  meta.textContent = datasetName(report.database);
  copy.append(badges, question, meta);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  button.dataset.id = report.investigation_id || "";
  button.textContent = "Open";
  button.disabled = running;
  item.append(copy, button);
  return item;
}

function markOpenReport() {
  for (const item of savedList.querySelectorAll(".saved-item")) {
    const selected = item.dataset.id === selectedId;
    const expanded = selected && !result.hidden && result.open;
    item.classList.toggle("is-open", expanded);
    const button = item.querySelector("button");
    if (!button) {
      continue;
    }
    button.textContent = expanded ? "Close" : "Open";
    if (selected) {
      button.setAttribute("aria-current", "true");
    } else {
      button.removeAttribute("aria-current");
    }
  }
}

function sortReports(reports) {
  return reports
    .map((report, index) => ({ report, index }))
    .sort((left, right) => {
      const group = successRank(left.report.status) - successRank(right.report.status);
      if (group !== 0) {
        return group;
      }
      return left.index - right.index;
    })
    .map((item) => item.report);
}

function successRank(status) {
  return status === "complete" ? 0 : 1;
}

function setBusy(busy) {
  running = busy;
  questionInput.disabled = busy;
  for (const input of document.querySelectorAll('input[name="dataset"]')) {
    input.disabled = busy;
  }
  runButton.disabled = busy;
  followButton.disabled = busy || !selectedId;
  for (const button of savedList.querySelectorAll("button")) {
    button.disabled = busy;
  }
}

function selectedDataset() {
  const chosen = document.querySelector('input[name="dataset"]:checked');
  return chosen ? chosen.value : "demo";
}

function showError(message) {
  requestError.textContent = message;
}

function setText(selector, value) {
  document.querySelector(selector).textContent = value;
}

function paragraph(value) {
  const element = document.createElement("p");
  element.textContent = value;
  return element;
}

function statusLabel(status) {
  const value = status || "unknown";
  if (value === "api_error") {
    return "API error";
  }
  return value.charAt(0).toUpperCase() + value.slice(1).replaceAll("_", " ");
}

function badgeClass(status) {
  if (status === "complete") {
    return "badge-complete";
  }
  if (status === "api_error") {
    return "badge-error";
  }
  if (status === "incomplete" || status === "context_limit" || status === "refused" || status === "invalid_question") {
    return "badge-incomplete";
  }
  return "";
}

function datasetName(database) {
  const path = (database && database.path) || "";
  if (path.endsWith("demo.sqlite")) {
    return "Demo";
  }
  if (path.endsWith("seed.sqlite")) {
    return "Seed";
  }
  if (!path) {
    return "Not recorded";
  }
  return path;
}

function evidenceLabel(evidenceId) {
  if (!evidenceId) {
    return "Evidence";
  }
  const match = String(evidenceId).match(/E[1-9][0-9]*$/);
  return match ? match[0] : String(evidenceId);
}
