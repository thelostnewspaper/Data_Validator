"use strict";
(() => {
  // media/diff.ts
  function renderDiff(diffText) {
    if (!diffText) {
      return '<div class="diff-container"><div class="diff-line context">No changes</div></div>';
    }
    const lines = diffText.split("\n");
    const htmlLines = [];
    for (const line of lines) {
      const escapedLine = escapeHtml(line);
      if (line.startsWith("+++") || line.startsWith("---")) {
        htmlLines.push(`<div class="diff-line header">${escapedLine}</div>`);
      } else if (line.startsWith("@@")) {
        htmlLines.push(`<div class="diff-line header">${escapedLine}</div>`);
      } else if (line.startsWith("+")) {
        htmlLines.push(`<div class="diff-line addition">${escapedLine}</div>`);
      } else if (line.startsWith("-")) {
        htmlLines.push(`<div class="diff-line deletion">${escapedLine}</div>`);
      } else {
        htmlLines.push(`<div class="diff-line context">${escapedLine}</div>`);
      }
    }
    return `<div class="diff-container">${htmlLines.join("")}</div>`;
  }
  function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  // media/main.ts
  var vscode = acquireVsCodeApi();
  var $loading = document.getElementById("loading");
  var $loadingMessage = document.getElementById("loading-message");
  var $summary = document.getElementById("summary");
  var $errorCount = document.getElementById("error-count");
  var $warningCount = document.getElementById("warning-count");
  var $passedCount = document.getElementById("passed-count");
  var $emptyState = document.getElementById("empty-state");
  var $checksSection = document.getElementById("checks-section");
  var $checksList = document.getElementById("checks-list");
  var $fixesSection = document.getElementById("fixes-section");
  var $fixesList = document.getElementById("fixes-list");
  var $aiSection = document.getElementById("ai-section");
  var $aiList = document.getElementById("ai-list");
  document.getElementById("btn-validate").addEventListener("click", () => {
    vscode.postMessage({ type: "validate" });
  });
  document.getElementById("btn-ai-fix").addEventListener("click", () => {
    vscode.postMessage({ type: "fixWithAI" });
  });
  document.getElementById("btn-settings").addEventListener("click", () => {
    vscode.postMessage({ type: "openSettings" });
  });
  window.addEventListener("message", (event) => {
    const msg = event.data;
    switch (msg.type) {
      case "validationResult":
        renderValidationResult(msg.data);
        break;
      case "remediationStream":
        renderRemediationOption(msg.data);
        break;
      case "remediationDone":
        hideLoading();
        break;
      case "remediationError":
        hideLoading();
        showError(msg.message);
        break;
      case "loading":
        showLoading(msg.message);
        break;
      case "error":
        hideLoading();
        showError(msg.message);
        break;
    }
  });
  function renderValidationResult(result) {
    hideLoading();
    $emptyState.classList.add("hidden");
    $errorCount.textContent = String(result.summary.failures);
    $warningCount.textContent = String(result.summary.warnings);
    $passedCount.textContent = String(result.summary.passed);
    $summary.classList.remove("hidden");
    renderChecks(result.checks);
    renderFixes(result.fixes);
  }
  function renderChecks(checks) {
    $checksList.innerHTML = "";
    const categories = /* @__PURE__ */ new Map();
    for (const check of checks) {
      const list = categories.get(check.category) || [];
      list.push(check);
      categories.set(check.category, list);
    }
    const sortedChecks = [...checks].sort((a, b) => {
      const order = { fail: 0, warn: 1, pass: 2 };
      return (order[a.status] ?? 3) - (order[b.status] ?? 3);
    });
    for (const check of sortedChecks) {
      const card = createCheckCard(check);
      $checksList.appendChild(card);
    }
    $checksSection.classList.toggle("hidden", checks.length === 0);
  }
  function createCheckCard(check) {
    const card = document.createElement("div");
    card.className = "check-card animate-in";
    const icon = document.createElement("span");
    icon.className = `check-icon ${check.status}`;
    icon.textContent = check.status === "fail" ? "\u2717" : check.status === "warn" ? "\u26A0" : "\u2713";
    card.appendChild(icon);
    const body = document.createElement("div");
    body.className = "check-body";
    const header = document.createElement("div");
    header.className = "check-header";
    const idBadge = document.createElement("span");
    idBadge.className = "check-id";
    idBadge.textContent = check.id;
    header.appendChild(idBadge);
    if (check.line > 0) {
      const lineBadge = document.createElement("span");
      lineBadge.className = "check-line";
      lineBadge.textContent = `L${check.line}`;
      header.appendChild(lineBadge);
    }
    body.appendChild(header);
    const message = document.createElement("div");
    message.className = "check-message";
    message.textContent = check.message;
    body.appendChild(message);
    if (check.detail) {
      const detail = document.createElement("div");
      detail.className = "check-detail";
      detail.textContent = check.detail;
      detail.style.display = "none";
      body.appendChild(detail);
      card.style.cursor = "pointer";
      card.addEventListener("click", () => {
        detail.style.display = detail.style.display === "none" ? "block" : "none";
      });
    }
    card.appendChild(body);
    return card;
  }
  function renderFixes(fixes) {
    $fixesList.innerHTML = "";
    for (let i = 0; i < fixes.length; i++) {
      const card = createFixCard(fixes[i], i);
      $fixesList.appendChild(card);
    }
    $fixesSection.classList.toggle("hidden", fixes.length === 0);
  }
  function createFixCard(fix, index) {
    const card = document.createElement("div");
    card.className = "fix-card animate-in";
    const header = document.createElement("div");
    header.className = "fix-header";
    const desc = document.createElement("span");
    desc.className = "fix-description";
    desc.textContent = fix.description;
    header.appendChild(desc);
    const conf = document.createElement("span");
    conf.className = "fix-confidence";
    conf.textContent = `${Math.round(fix.confidence * 100)}%`;
    header.appendChild(conf);
    card.appendChild(header);
    if (fix.diff) {
      const diffContainer = document.createElement("div");
      diffContainer.className = "fix-diff";
      diffContainer.innerHTML = renderDiff(fix.diff);
      card.appendChild(diffContainer);
    }
    const actions = document.createElement("div");
    actions.className = "fix-actions";
    const acceptBtn = document.createElement("button");
    acceptBtn.className = "btn btn-success btn-sm";
    acceptBtn.textContent = "\u2713 Accept";
    acceptBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      vscode.postMessage({ type: "acceptFix", fixIndex: index });
    });
    actions.appendChild(acceptBtn);
    const rejectBtn = document.createElement("button");
    rejectBtn.className = "btn btn-danger btn-sm";
    rejectBtn.textContent = "\u2717 Reject";
    rejectBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      card.remove();
    });
    actions.appendChild(rejectBtn);
    const undoBtn = document.createElement("button");
    undoBtn.className = "btn btn-ghost btn-sm";
    undoBtn.textContent = "\u21A9 Undo";
    undoBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      vscode.postMessage({ type: "undoFix" });
    });
    actions.appendChild(undoBtn);
    card.appendChild(actions);
    return card;
  }
  function renderRemediationOption(option) {
    $aiSection.classList.remove("hidden");
    const card = document.createElement("div");
    card.className = `ai-card animate-in ${option.failed ? "failed" : ""}`;
    const impact = document.createElement("span");
    impact.className = `ai-impact ${option.impact}`;
    impact.textContent = `${option.impact} impact`;
    card.appendChild(impact);
    const title = document.createElement("div");
    title.className = "ai-title";
    title.textContent = option.title;
    card.appendChild(title);
    if (option.root_cause) {
      const rootCause = document.createElement("div");
      rootCause.className = "ai-root-cause";
      rootCause.textContent = option.root_cause;
      card.appendChild(rootCause);
    }
    if (option.fix_explanation) {
      const explanation = document.createElement("div");
      explanation.className = "ai-explanation";
      explanation.textContent = option.fix_explanation;
      card.appendChild(explanation);
    }
    if (option.diff) {
      const diffContainer = document.createElement("div");
      diffContainer.className = "fix-diff";
      diffContainer.innerHTML = renderDiff(option.diff);
      card.appendChild(diffContainer);
    }
    if (option.failed && option.failure_reason) {
      const failedReason = document.createElement("div");
      failedReason.className = "ai-failed-reason";
      failedReason.textContent = `\u26A0 Gate rejected: ${option.failure_reason}`;
      card.appendChild(failedReason);
    }
    if (!option.failed) {
      const actions = document.createElement("div");
      actions.className = "fix-actions";
      const acceptBtn = document.createElement("button");
      acceptBtn.className = "btn btn-success btn-sm";
      acceptBtn.textContent = "\u2713 Accept";
      acceptBtn.addEventListener("click", () => {
        vscode.postMessage({
          type: "acceptRemediation",
          optionIndex: 0,
          dagCode: option.dag_code
        });
      });
      actions.appendChild(acceptBtn);
      const rejectBtn = document.createElement("button");
      rejectBtn.className = "btn btn-danger btn-sm";
      rejectBtn.textContent = "\u2717 Reject";
      rejectBtn.addEventListener("click", () => {
        card.remove();
      });
      actions.appendChild(rejectBtn);
      card.appendChild(actions);
    }
    $aiList.appendChild(card);
  }
  function showLoading(message) {
    $loadingMessage.textContent = message;
    $loading.classList.remove("hidden");
    $emptyState.classList.add("hidden");
  }
  function hideLoading() {
    $loading.classList.add("hidden");
  }
  function showError(message) {
    const card = createCheckCard({
      id: "ERROR",
      status: "fail",
      category: "syntax",
      message,
      detail: "",
      line: 0,
      source_rule: ""
    });
    $checksList.appendChild(card);
    $checksSection.classList.remove("hidden");
  }
})();
//# sourceMappingURL=main.js.map
