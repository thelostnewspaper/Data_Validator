/**
 * Command handlers — the user-facing actions.
 *
 * Commands:
 * - ai-validator.validate — validate the active file
 * - ai-validator.fixWithAI — AI-powered fix generation
 * - ai-validator.openPanel — open the webview panel
 * - ai-validator.setApiKey — store an API key
 * - ai-validator.addConnectionProfile — add a connection
 */

import * as vscode from 'vscode';
import { EngineClient } from './engineClient';
import { DiagnosticsManager } from './diagnostics';
import { ValidatorCodeActionProvider } from './codeActions';
import { StatusBarManager } from './statusBar';
import { SecretManager } from './secrets';
import { ValidatorPanel } from './webview/panel';
import { getEnabledPacks, getAiProvider, getAiModel } from './config';
import { ValidationResult, ValidateRequest } from './types';

export class CommandHandlers implements vscode.Disposable {
    private lastValidationResult: ValidationResult | undefined;
    private panel: ValidatorPanel | undefined;

    constructor(
        private readonly engine: EngineClient,
        private readonly diagnostics: DiagnosticsManager,
        private readonly codeActions: ValidatorCodeActionProvider,
        private readonly statusBar: StatusBarManager,
        private readonly secrets: SecretManager,
        private readonly extensionUri: vscode.Uri,
    ) {}

    /**
     * Validate the current file.
     */
    async validateCurrentFile(): Promise<ValidationResult | undefined> {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor to validate.');
            return undefined;
        }

        const document = editor.document;
        this.statusBar.setLoading();

        try {
            const request: ValidateRequest = {
                file_path: document.uri.fsPath,
                content: document.getText(),
                enabled_packs: getEnabledPacks(),
            };

            const result = await this.engine.validate(request);

            if (result) {
                // Update diagnostics (squiggles)
                this.diagnostics.update(document.uri, result.checks);

                // Update code actions (lightbulbs)
                this.codeActions.updateFixes(document.uri, result.fixes);

                // Update status bar
                this.statusBar.update(result.summary);

                // Update panel if open
                if (this.panel) {
                    this.panel.postValidationResult(result);
                }

                this.lastValidationResult = result;

                // Show summary notification
                if (result.summary.failures > 0) {
                    vscode.window.showWarningMessage(
                        `AI Validator: ${result.summary.failures} error(s), ${result.summary.warnings} warning(s)`,
                    );
                }
            }

            return result;
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`Validation failed: ${msg}`);
            this.statusBar.setIdle();
            return undefined;
        }
    }

    /**
     * Fix the current file with AI.
     */
    async fixWithAI(): Promise<void> {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor.');
            return;
        }

        // Ensure we have a recent validation result
        if (!this.lastValidationResult) {
            await this.validateCurrentFile();
        }

        if (!this.lastValidationResult) {
            vscode.window.showWarningMessage(
                'Run validation first before using AI fixes.',
            );
            return;
        }

        // Check for API key
        const provider = getAiProvider();
        let apiKey = await this.secrets.getApiKey(provider);

        if (!apiKey) {
            apiKey = await this.secrets.promptForApiKey(provider);
            if (!apiKey) {
                return;
            }
        }

        // Open the panel for streaming display
        this.openPanel();

        if (this.panel) {
            this.panel.postMessage({ type: 'loading', message: 'Generating AI fixes...' });
        }

        try {
            await this.engine.aiRemediate({
                file_path: editor.document.uri.fsPath,
                content: editor.document.getText(),
                checks: this.lastValidationResult.checks,
                fixes: this.lastValidationResult.fixes,
                api_key: apiKey,
                provider: provider,
                model: getAiModel(),
            });
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`AI remediation failed: ${msg}`);
        }
    }

    /**
     * Open the validator panel.
     */
    openPanel(): void {
        if (!this.panel) {
            this.panel = new ValidatorPanel(this.extensionUri, this);
        }
        this.panel.reveal();

        // Send last result if available
        if (this.lastValidationResult) {
            this.panel.postValidationResult(this.lastValidationResult);
        }
    }

    /**
     * Post a remediation option to the panel.
     */
    postRemediationStream(option: any): void {
        if (this.panel) {
            this.panel.postRemediationStream(option);
        }
    }

    postRemediationDone(): void {
        if (this.panel) {
            this.panel.postMessage({ type: 'remediationDone' });
        }
    }

    postRemediationError(message: string): void {
        if (this.panel) {
            this.panel.postMessage({ type: 'remediationError', message });
        }
    }

    /**
     * Set an AI provider API key.
     */
    async setApiKey(): Promise<void> {
        const provider = await vscode.window.showQuickPick(
            ['claude', 'gemini', 'openai'],
            { title: 'Select AI Provider' },
        );

        if (provider) {
            await this.secrets.promptForApiKey(provider);
        }
    }

    /**
     * Handle an accepted fix from the panel.
     */
    async applyFix(fixIndex: number): Promise<void> {
        if (!this.lastValidationResult) {
            return;
        }

        const fix = this.lastValidationResult.fixes[fixIndex];
        if (!fix) {
            return;
        }

        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return;
        }

        const text = editor.document.getText();
        const index = text.indexOf(fix.old_text);

        if (index >= 0) {
            const startPos = editor.document.positionAt(index);
            const endPos = editor.document.positionAt(index + fix.old_text.length);

            await editor.edit((editBuilder) => {
                editBuilder.replace(
                    new vscode.Range(startPos, endPos),
                    fix.new_text,
                );
            });

            // Re-validate after applying the fix
            await this.validateCurrentFile();
        }
    }

    /**
     * Handle an accepted AI remediation from the panel.
     */
    async applyRemediation(dagCode: string): Promise<void> {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return;
        }

        const fullRange = new vscode.Range(
            new vscode.Position(0, 0),
            editor.document.positionAt(editor.document.getText().length),
        );

        await editor.edit((editBuilder) => {
            editBuilder.replace(fullRange, dagCode);
        });

        // Re-validate after applying the remediation
        await this.validateCurrentFile();
    }

    /**
     * Undo the last fix.
     */
    async undoFix(): Promise<void> {
        await vscode.commands.executeCommand('undo');
        // Re-validate after undo
        await this.validateCurrentFile();
    }

    dispose(): void {
        this.panel?.dispose();
    }
}
