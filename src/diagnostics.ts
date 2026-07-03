/**
 * Diagnostics — maps CheckResult[] → VS Code Diagnostic[] (squiggles).
 *
 * fail → DiagnosticSeverity.Error (red)
 * warn → DiagnosticSeverity.Warning (yellow)
 * pass → cleared
 */

import * as vscode from 'vscode';
import { CheckResult } from './types';

export class DiagnosticsManager implements vscode.Disposable {
    private readonly collection: vscode.DiagnosticCollection;

    constructor() {
        this.collection = vscode.languages.createDiagnosticCollection('ai-validator');
    }

    /**
     * Update diagnostics for a file from check results.
     */
    update(uri: vscode.Uri, checks: CheckResult[]): void {
        const diagnostics: vscode.Diagnostic[] = [];

        for (const check of checks) {
            if (check.status === 'pass') {
                continue;
            }

            const severity = check.status === 'fail'
                ? vscode.DiagnosticSeverity.Error
                : vscode.DiagnosticSeverity.Warning;

            // Build the range from line/column info
            const startLine = Math.max(0, (check.line || 1) - 1);
            const startCol = Math.max(0, check.column || 0);
            const endLine = check.end_line
                ? Math.max(0, check.end_line - 1)
                : startLine;
            const endCol = check.end_column || startCol + 20;

            const range = new vscode.Range(
                new vscode.Position(startLine, startCol),
                new vscode.Position(endLine, endCol),
            );

            const diagnostic = new vscode.Diagnostic(range, check.message, severity);
            diagnostic.code = check.id;
            diagnostic.source = 'AI Validator';

            if (check.detail) {
                diagnostic.message += `\n\n${check.detail}`;
            }

            diagnostics.push(diagnostic);
        }

        this.collection.set(uri, diagnostics);
    }

    /**
     * Clear diagnostics for a file.
     */
    clear(uri: vscode.Uri): void {
        this.collection.delete(uri);
    }

    /**
     * Clear all diagnostics.
     */
    clearAll(): void {
        this.collection.clear();
    }

    dispose(): void {
        this.collection.dispose();
    }
}
