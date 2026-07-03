/**
 * Webview panel — creates and manages the validator dashboard.
 *
 * CSP-hardened, nonce-gated scripts, localResourceRoots restricted
 * to the media/ folder. postMessage protocol for bidirectional
 * communication with the extension host.
 */

import * as vscode from 'vscode';
import { ValidationResult, RemediationOption, ExtensionMessage, WebviewMessage } from '../types';

export class ValidatorPanel implements vscode.Disposable {
    public static readonly viewType = 'aiValidator.panel';

    private panel: vscode.WebviewPanel | undefined;
    private disposables: vscode.Disposable[] = [];

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly commandHandler: {
            applyFix(index: number): Promise<void>;
            applyRemediation(dagCode: string): Promise<void>;
            undoFix(): Promise<void>;
            validateCurrentFile(): Promise<any>;
            fixWithAI(): Promise<void>;
        },
    ) {}

    /**
     * Create or reveal the panel.
     */
    reveal(): void {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Beside);
            return;
        }

        const mediaPath = vscode.Uri.joinPath(this.extensionUri, 'media');

        this.panel = vscode.window.createWebviewPanel(
            ValidatorPanel.viewType,
            'AI Validator',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                localResourceRoots: [mediaPath],
                retainContextWhenHidden: true,
            },
        );

        this.panel.webview.html = this.getWebviewContent(this.panel.webview);

        // Handle messages from the webview
        this.panel.webview.onDidReceiveMessage(
            (msg: WebviewMessage) => this.handleWebviewMessage(msg),
            undefined,
            this.disposables,
        );

        this.panel.onDidDispose(
            () => {
                this.panel = undefined;
                this.disposables.forEach((d) => d.dispose());
                this.disposables = [];
            },
            undefined,
            this.disposables,
        );
    }

    /**
     * Send a validation result to the webview.
     */
    postValidationResult(result: ValidationResult): void {
        this.postMessage({ type: 'validationResult', data: result });
    }

    /**
     * Send a remediation stream event to the webview.
     */
    postRemediationStream(option: RemediationOption): void {
        this.postMessage({ type: 'remediationStream', data: option });
    }

    /**
     * Send a generic message to the webview.
     */
    postMessage(message: ExtensionMessage): void {
        this.panel?.webview.postMessage(message);
    }

    private async handleWebviewMessage(msg: WebviewMessage): Promise<void> {
        switch (msg.type) {
            case 'validate':
                await this.commandHandler.validateCurrentFile();
                break;
            case 'fixWithAI':
                await this.commandHandler.fixWithAI();
                break;
            case 'acceptFix':
                await this.commandHandler.applyFix(msg.fixIndex);
                break;
            case 'rejectFix':
                // No action needed — just dismiss
                break;
            case 'undoFix':
                await this.commandHandler.undoFix();
                break;
            case 'acceptRemediation':
                await this.commandHandler.applyRemediation(msg.dagCode);
                break;
            case 'openSettings':
                vscode.commands.executeCommand(
                    'workbench.action.openSettings',
                    'ai-validator',
                );
                break;
        }
    }

    private getWebviewContent(webview: vscode.Webview): string {
        const mediaUri = vscode.Uri.joinPath(this.extensionUri, 'media');
        const scriptUri = webview.asWebviewUri(
            vscode.Uri.joinPath(mediaUri, 'main.js'),
        );
        const styleUri = webview.asWebviewUri(
            vscode.Uri.joinPath(mediaUri, 'styles.css'),
        );

        const nonce = getNonce();

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'none';
                   img-src ${webview.cspSource} https:;
                   script-src 'nonce-${nonce}';
                   style-src ${webview.cspSource} 'unsafe-inline';
                   font-src ${webview.cspSource};">
    <link href="${styleUri}" rel="stylesheet">
    <title>AI Validator</title>
</head>
<body>
    <div id="app">
        <header id="header">
            <div class="header-left">
                <span class="header-icon">🛡️</span>
                <h1>AI Validator</h1>
            </div>
            <div class="header-actions">
                <button id="btn-validate" class="btn btn-primary" title="Validate">
                    <span class="codicon codicon-play"></span> Validate
                </button>
                <button id="btn-ai-fix" class="btn btn-accent" title="Fix with AI">
                    <span class="codicon codicon-sparkle"></span> Fix with AI
                </button>
                <button id="btn-settings" class="btn btn-ghost" title="Settings">
                    <span class="codicon codicon-gear"></span>
                </button>
            </div>
        </header>

        <div id="loading" class="loading hidden">
            <div class="spinner"></div>
            <span id="loading-message">Validating...</span>
        </div>

        <div id="summary" class="summary hidden">
            <div class="summary-card summary-errors" id="summary-errors">
                <span class="summary-count" id="error-count">0</span>
                <span class="summary-label">Errors</span>
            </div>
            <div class="summary-card summary-warnings" id="summary-warnings">
                <span class="summary-count" id="warning-count">0</span>
                <span class="summary-label">Warnings</span>
            </div>
            <div class="summary-card summary-passed" id="summary-passed">
                <span class="summary-count" id="passed-count">0</span>
                <span class="summary-label">Passed</span>
            </div>
        </div>

        <div id="content">
            <div id="empty-state" class="empty-state">
                <div class="empty-icon">🔍</div>
                <h2>No validation results yet</h2>
                <p>Open a supported file and click <strong>Validate</strong>, or save to auto-validate.</p>
            </div>

            <div id="checks-section" class="section hidden">
                <h2 class="section-title">
                    <span class="section-icon">📋</span> Check Results
                </h2>
                <div id="checks-list" class="checks-list"></div>
            </div>

            <div id="fixes-section" class="section hidden">
                <h2 class="section-title">
                    <span class="section-icon">🔧</span> Suggested Fixes
                </h2>
                <div id="fixes-list" class="fixes-list"></div>
            </div>

            <div id="ai-section" class="section hidden">
                <h2 class="section-title">
                    <span class="section-icon">✨</span> AI Remediation
                </h2>
                <div id="ai-list" class="ai-list"></div>
            </div>
        </div>
    </div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
    }

    dispose(): void {
        this.panel?.dispose();
        this.disposables.forEach((d) => d.dispose());
    }
}

function getNonce(): string {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}
