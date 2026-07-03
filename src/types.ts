/**
 * TypeScript mirrors of the Python engine data models.
 *
 * MUST be kept in sync with engine/core/models.py and engine/protocol.py.
 * These are the ONLY types that cross the process boundary via JSON-RPC.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type CheckStatus = 'pass' | 'warn' | 'fail';

export type CheckCategory =
    | 'syntax'
    | 'structure'
    | 'variables'
    | 'columns'
    | 'dependencies'
    | 'connections'
    | 'security'
    | 'best_practices';

export type FixImpact = 'low' | 'medium' | 'high';

// ---------------------------------------------------------------------------
// Core check result
// ---------------------------------------------------------------------------

export interface CheckResult {
    id: string;
    status: CheckStatus;
    category: CheckCategory;
    message: string;
    detail: string;
    line: number;
    column: number;
    end_line: number;
    end_column: number;
    source_rule: string;
}

// ---------------------------------------------------------------------------
// Deterministic fix suggestion
// ---------------------------------------------------------------------------

export interface SuggestedFix {
    check_id: string;
    description: string;
    old_text: string;
    new_text: string;
    diff: string;
    confidence: number;
    line: number;
    column: number;
}

// ---------------------------------------------------------------------------
// Airflow connection fix
// ---------------------------------------------------------------------------

export interface AirflowConnectionFix {
    conn_id: string;
    conn_type: string;
    host: string;
    port: number;
    schema: string;
    login: string;
    extra: Record<string, unknown>;
    description: string;
}

// ---------------------------------------------------------------------------
// Validation result
// ---------------------------------------------------------------------------

export interface ValidationSummary {
    total: number;
    passed: number;
    warnings: number;
    failures: number;
}

export interface ValidationResult {
    file_path: string;
    checks: CheckResult[];
    fixes: SuggestedFix[];
    connection_fixes: AirflowConnectionFix[];
    summary: ValidationSummary;
}

// ---------------------------------------------------------------------------
// AI remediation option
// ---------------------------------------------------------------------------

export interface CodeChange {
    file_path: string;
    old_content: string;
    new_content: string;
    description: string;
}

export interface RemediationOption {
    impact: FixImpact;
    title: string;
    root_cause: string;
    fix_explanation: string;
    changes: CodeChange[];
    dag_code: string;
    diff: string;
    failed: boolean;
    failure_reason: string;
    checks_after: CheckResult[];
    status?: 'streaming' | 'complete' | 'error';
}

// ---------------------------------------------------------------------------
// JSON-RPC method names (mirrors engine/protocol.py)
// ---------------------------------------------------------------------------

export const Methods = {
    VALIDATE: 'validate',
    GET_PACKS: 'getPacks',
    AI_REMEDIATE: 'aiRemediate',
    AI_REMEDIATE_STREAM: 'aiRemediate/stream',
    AI_REMEDIATE_DONE: 'aiRemediate/done',
    AI_REMEDIATE_ERROR: 'aiRemediate/error',
    CHECK_CONNECTION: 'checkConnection',
    CREATE_AIRFLOW_CONNECTION: 'createAirflowConnection',
    SHUTDOWN: 'shutdown',
    INITIALIZED: 'initialized',
} as const;

// ---------------------------------------------------------------------------
// Request / Response types
// ---------------------------------------------------------------------------

export interface ValidateRequest {
    file_path: string;
    content: string;
    connections?: Record<string, unknown>;
    enabled_packs?: string[];
}

export interface AiRemediateRequest {
    file_path: string;
    content: string;
    checks: CheckResult[];
    fixes?: SuggestedFix[];
    api_key: string;
    provider?: string;
    model?: string;
    connections?: Record<string, unknown>;
}

export interface PackInfo {
    id: string;
    name: string;
    description: string;
}

export interface GetPacksResponse {
    packs: PackInfo[];
}

// ---------------------------------------------------------------------------
// Webview ↔ Extension postMessage protocol
// ---------------------------------------------------------------------------

export type WebviewMessage =
    | { type: 'validate'; }
    | { type: 'fixWithAI'; }
    | { type: 'acceptFix'; fixIndex: number; }
    | { type: 'rejectFix'; fixIndex: number; }
    | { type: 'undoFix'; }
    | { type: 'acceptRemediation'; optionIndex: number; dagCode: string; }
    | { type: 'rejectRemediation'; optionIndex: number; }
    | { type: 'openSettings'; };

export type ExtensionMessage =
    | { type: 'validationResult'; data: ValidationResult; }
    | { type: 'remediationStream'; data: RemediationOption; }
    | { type: 'remediationDone'; }
    | { type: 'remediationError'; message: string; }
    | { type: 'fixApplied'; fixIndex: number; }
    | { type: 'fixUndone'; }
    | { type: 'loading'; message: string; }
    | { type: 'error'; message: string; };
