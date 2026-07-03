/**
 * Webview main application — renders check sections, fix cards,
 * AI remediation stream. Sends accept/reject/undo back to the extension.
 *
 * All DOM updates use textContent (never innerHTML with untrusted data).
 */

import { renderDiff } from './diff';

// Acquire the VS Code API
declare function acquireVsCodeApi(): {
    postMessage(message: unknown): void;
    getState(): unknown;
    setState(state: unknown): void;
};

const vscode = acquireVsCodeApi();

// ---------------------------------------------------------------------------
// Types (subset mirroring types.ts)
// ---------------------------------------------------------------------------

interface CheckResult {
    id: string;
    status: 'pass' | 'warn' | 'fail';
    category: string;
    message: string;
    detail: string;
    line: number;
    source_rule: string;
}

interface SuggestedFix {
    check_id: string;
    description: string;
    old_text: string;
    new_text: string;
    diff: string;
    confidence: number;
    line: number;
}

interface ValidationSummary {
    total: number;
    passed: number;
    warnings: number;
    failures: number;
}

interface ValidationResult {
    file_path: string;
    checks: CheckResult[];
    fixes: SuggestedFix[];
    summary: ValidationSummary;
}

interface RemediationOption {
    impact: 'low' | 'medium' | 'high';
    title: string;
    root_cause: string;
    fix_explanation: string;
    dag_code: string;
    diff: string;
    failed: boolean;
    failure_reason: string;
}

type ExtensionMessage =
    | { type: 'validationResult'; data: ValidationResult }
    | { type: 'remediationStream'; data: RemediationOption }
    | { type: 'remediationDone' }
    | { type: 'remediationError'; message: string }
    | { type: 'fixApplied'; fixIndex: number }
    | { type: 'fixUndone' }
    | { type: 'loading'; message: string }
    | { type: 'error'; message: string };

// ---------------------------------------------------------------------------
// DOM elements
// ---------------------------------------------------------------------------

const $loading = document.getElementById('loading')!;
const $loadingMessage = document.getElementById('loading-message')!;
const $summary = document.getElementById('summary')!;
const $errorCount = document.getElementById('error-count')!;
const $warningCount = document.getElementById('warning-count')!;
const $passedCount = document.getElementById('passed-count')!;
const $emptyState = document.getElementById('empty-state')!;
const $checksSection = document.getElementById('checks-section')!;
const $checksList = document.getElementById('checks-list')!;
const $fixesSection = document.getElementById('fixes-section')!;
const $fixesList = document.getElementById('fixes-list')!;
const $aiSection = document.getElementById('ai-section')!;
const $aiList = document.getElementById('ai-list')!;

// Buttons
document.getElementById('btn-validate')!.addEventListener('click', () => {
    vscode.postMessage({ type: 'validate' });
});

document.getElementById('btn-ai-fix')!.addEventListener('click', () => {
    vscode.postMessage({ type: 'fixWithAI' });
});

document.getElementById('btn-settings')!.addEventListener('click', () => {
    vscode.postMessage({ type: 'openSettings' });
});

// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------

window.addEventListener('message', (event) => {
    const msg: ExtensionMessage = event.data;

    switch (msg.type) {
        case 'validationResult':
            renderValidationResult(msg.data);
            break;
        case 'remediationStream':
            renderRemediationOption(msg.data);
            break;
        case 'remediationDone':
            hideLoading();
            break;
        case 'remediationError':
            hideLoading();
            showError(msg.message);
            break;
        case 'loading':
            showLoading(msg.message);
            break;
        case 'error':
            hideLoading();
            showError(msg.message);
            break;
    }
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderValidationResult(result: ValidationResult): void {
    hideLoading();
    $emptyState.classList.add('hidden');

    // Summary
    $errorCount.textContent = String(result.summary.failures);
    $warningCount.textContent = String(result.summary.warnings);
    $passedCount.textContent = String(result.summary.passed);
    $summary.classList.remove('hidden');

    // Checks
    renderChecks(result.checks);

    // Fixes
    renderFixes(result.fixes);
}

function renderChecks(checks: CheckResult[]): void {
    $checksList.innerHTML = '';

    // Group by category
    const categories = new Map<string, CheckResult[]>();
    for (const check of checks) {
        const list = categories.get(check.category) || [];
        list.push(check);
        categories.set(check.category, list);
    }

    // Sort: failures first, then warnings, then passes
    const sortedChecks = [...checks].sort((a, b) => {
        const order = { fail: 0, warn: 1, pass: 2 };
        return (order[a.status] ?? 3) - (order[b.status] ?? 3);
    });

    for (const check of sortedChecks) {
        const card = createCheckCard(check);
        $checksList.appendChild(card);
    }

    $checksSection.classList.toggle('hidden', checks.length === 0);
}

function createCheckCard(check: CheckResult): HTMLElement {
    const card = document.createElement('div');
    card.className = 'check-card animate-in';

    // Icon
    const icon = document.createElement('span');
    icon.className = `check-icon ${check.status}`;
    icon.textContent = check.status === 'fail' ? '✗' : check.status === 'warn' ? '⚠' : '✓';
    card.appendChild(icon);

    // Body
    const body = document.createElement('div');
    body.className = 'check-body';

    // Header row
    const header = document.createElement('div');
    header.className = 'check-header';

    const idBadge = document.createElement('span');
    idBadge.className = 'check-id';
    idBadge.textContent = check.id;
    header.appendChild(idBadge);

    if (check.line > 0) {
        const lineBadge = document.createElement('span');
        lineBadge.className = 'check-line';
        lineBadge.textContent = `L${check.line}`;
        header.appendChild(lineBadge);
    }

    body.appendChild(header);

    // Message
    const message = document.createElement('div');
    message.className = 'check-message';
    message.textContent = check.message;
    body.appendChild(message);

    // Detail (collapsible)
    if (check.detail) {
        const detail = document.createElement('div');
        detail.className = 'check-detail';
        detail.textContent = check.detail;
        detail.style.display = 'none';
        body.appendChild(detail);

        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
            detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
        });
    }

    card.appendChild(body);
    return card;
}

function renderFixes(fixes: SuggestedFix[]): void {
    $fixesList.innerHTML = '';

    for (let i = 0; i < fixes.length; i++) {
        const card = createFixCard(fixes[i], i);
        $fixesList.appendChild(card);
    }

    $fixesSection.classList.toggle('hidden', fixes.length === 0);
}

function createFixCard(fix: SuggestedFix, index: number): HTMLElement {
    const card = document.createElement('div');
    card.className = 'fix-card animate-in';

    // Header
    const header = document.createElement('div');
    header.className = 'fix-header';

    const desc = document.createElement('span');
    desc.className = 'fix-description';
    desc.textContent = fix.description;
    header.appendChild(desc);

    const conf = document.createElement('span');
    conf.className = 'fix-confidence';
    conf.textContent = `${Math.round(fix.confidence * 100)}%`;
    header.appendChild(conf);

    card.appendChild(header);

    // Diff preview
    if (fix.diff) {
        const diffContainer = document.createElement('div');
        diffContainer.className = 'fix-diff';
        diffContainer.innerHTML = renderDiff(fix.diff);
        card.appendChild(diffContainer);
    }

    // Actions
    const actions = document.createElement('div');
    actions.className = 'fix-actions';

    const acceptBtn = document.createElement('button');
    acceptBtn.className = 'btn btn-success btn-sm';
    acceptBtn.textContent = '✓ Accept';
    acceptBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        vscode.postMessage({ type: 'acceptFix', fixIndex: index });
    });
    actions.appendChild(acceptBtn);

    const rejectBtn = document.createElement('button');
    rejectBtn.className = 'btn btn-danger btn-sm';
    rejectBtn.textContent = '✗ Reject';
    rejectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        card.remove();
    });
    actions.appendChild(rejectBtn);

    const undoBtn = document.createElement('button');
    undoBtn.className = 'btn btn-ghost btn-sm';
    undoBtn.textContent = '↩ Undo';
    undoBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        vscode.postMessage({ type: 'undoFix' });
    });
    actions.appendChild(undoBtn);

    card.appendChild(actions);
    return card;
}

function renderRemediationOption(option: RemediationOption): void {
    $aiSection.classList.remove('hidden');

    const card = document.createElement('div');
    card.className = `ai-card animate-in ${option.failed ? 'failed' : ''}`;

    // Impact badge
    const impact = document.createElement('span');
    impact.className = `ai-impact ${option.impact}`;
    impact.textContent = `${option.impact} impact`;
    card.appendChild(impact);

    // Title
    const title = document.createElement('div');
    title.className = 'ai-title';
    title.textContent = option.title;
    card.appendChild(title);

    // Root cause
    if (option.root_cause) {
        const rootCause = document.createElement('div');
        rootCause.className = 'ai-root-cause';
        rootCause.textContent = option.root_cause;
        card.appendChild(rootCause);
    }

    // Fix explanation
    if (option.fix_explanation) {
        const explanation = document.createElement('div');
        explanation.className = 'ai-explanation';
        explanation.textContent = option.fix_explanation;
        card.appendChild(explanation);
    }

    // Diff
    if (option.diff) {
        const diffContainer = document.createElement('div');
        diffContainer.className = 'fix-diff';
        diffContainer.innerHTML = renderDiff(option.diff);
        card.appendChild(diffContainer);
    }

    // Failed reason
    if (option.failed && option.failure_reason) {
        const failedReason = document.createElement('div');
        failedReason.className = 'ai-failed-reason';
        failedReason.textContent = `⚠ Gate rejected: ${option.failure_reason}`;
        card.appendChild(failedReason);
    }

    // Actions (only if not failed)
    if (!option.failed) {
        const actions = document.createElement('div');
        actions.className = 'fix-actions';

        const acceptBtn = document.createElement('button');
        acceptBtn.className = 'btn btn-success btn-sm';
        acceptBtn.textContent = '✓ Accept';
        acceptBtn.addEventListener('click', () => {
            vscode.postMessage({
                type: 'acceptRemediation',
                optionIndex: 0,
                dagCode: option.dag_code,
            });
        });
        actions.appendChild(acceptBtn);

        const rejectBtn = document.createElement('button');
        rejectBtn.className = 'btn btn-danger btn-sm';
        rejectBtn.textContent = '✗ Reject';
        rejectBtn.addEventListener('click', () => {
            card.remove();
        });
        actions.appendChild(rejectBtn);

        card.appendChild(actions);
    }

    $aiList.appendChild(card);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function showLoading(message: string): void {
    $loadingMessage.textContent = message;
    $loading.classList.remove('hidden');
    $emptyState.classList.add('hidden');
}

function hideLoading(): void {
    $loading.classList.add('hidden');
}

function showError(message: string): void {
    // Show error as a check card
    const card = createCheckCard({
        id: 'ERROR',
        status: 'fail',
        category: 'syntax',
        message: message,
        detail: '',
        line: 0,
        source_rule: '',
    });
    $checksList.appendChild(card);
    $checksSection.classList.remove('hidden');
}
