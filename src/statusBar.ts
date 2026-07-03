/**
 * Status bar — shows pass/warn/fail summary for the active file.
 *
 * ✅ 0 errors, 0 warnings (green)
 * ⚠️ 0 errors, 3 warnings (yellow)
 * ❌ 2 errors, 1 warning (red)
 *
 * Click opens the panel.
 */

import * as vscode from 'vscode';
import { ValidationSummary } from './types';

export class StatusBarManager implements vscode.Disposable {
    private readonly item: vscode.StatusBarItem;

    constructor() {
        this.item = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Left,
            100,
        );
        this.item.command = 'ai-validator.openPanel';
        this.item.tooltip = 'AI Validator — Click to open panel';
        this.item.show();
        this.setIdle();
    }

    /**
     * Update the status bar with validation results.
     */
    update(summary: ValidationSummary): void {
        if (summary.failures > 0) {
            this.item.text = `$(error) ${summary.failures} error${summary.failures !== 1 ? 's' : ''}, ${summary.warnings} warning${summary.warnings !== 1 ? 's' : ''}`;
            this.item.backgroundColor = new vscode.ThemeColor(
                'statusBarItem.errorBackground',
            );
        } else if (summary.warnings > 0) {
            this.item.text = `$(warning) ${summary.warnings} warning${summary.warnings !== 1 ? 's' : ''}`;
            this.item.backgroundColor = new vscode.ThemeColor(
                'statusBarItem.warningBackground',
            );
        } else if (summary.total > 0) {
            this.item.text = `$(check) All ${summary.total} checks passed`;
            this.item.backgroundColor = undefined;
        } else {
            this.setIdle();
        }
    }

    /**
     * Show a loading state.
     */
    setLoading(): void {
        this.item.text = '$(sync~spin) Validating...';
        this.item.backgroundColor = undefined;
    }

    /**
     * Show the idle state.
     */
    setIdle(): void {
        this.item.text = '$(shield) AI Validator';
        this.item.backgroundColor = undefined;
    }

    dispose(): void {
        this.item.dispose();
    }
}
