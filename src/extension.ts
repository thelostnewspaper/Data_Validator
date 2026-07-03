/**
 * Extension entry point — activate() / deactivate().
 *
 * Registers commands, spawns the Python engine, sets up diagnostics,
 * code actions, status bar, auto-validation on save/open.
 */

import * as vscode from 'vscode';
import { EngineClient } from './engineClient';
import { DiagnosticsManager } from './diagnostics';
import { ValidatorCodeActionProvider } from './codeActions';
import { StatusBarManager } from './statusBar';
import { SecretManager } from './secrets';
import { CommandHandlers } from './commands';
import { getValidateOnSave, getValidateOnOpen } from './config';

let engine: EngineClient;
let commands: CommandHandlers;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // Initialize components
    engine = new EngineClient(context.extensionPath);
    const diagnostics = new DiagnosticsManager();
    const codeActions = new ValidatorCodeActionProvider();
    const statusBar = new StatusBarManager();
    const secrets = new SecretManager(context.secrets);

    commands = new CommandHandlers(
        engine,
        diagnostics,
        codeActions,
        statusBar,
        secrets,
        context.extensionUri,
    );

    // Register streaming handlers
    engine.onRemediationStream((option) => {
        commands.openPanel();
        commands.postRemediationStream(option);
    });

    engine.onRemediationDone(() => {
        commands.postRemediationDone();
    });

    engine.onRemediationError((message) => {
        commands.postRemediationError(message);
    });

    // Start the engine
    await engine.start();

    // -------------------------------------------------------------------
    // Register commands
    // -------------------------------------------------------------------

    context.subscriptions.push(
        vscode.commands.registerCommand(
            'ai-validator.validate',
            () => commands.validateCurrentFile(),
        ),
        vscode.commands.registerCommand(
            'ai-validator.fixWithAI',
            () => commands.fixWithAI(),
        ),
        vscode.commands.registerCommand(
            'ai-validator.openPanel',
            () => commands.openPanel(),
        ),
        vscode.commands.registerCommand(
            'ai-validator.setApiKey',
            () => commands.setApiKey(),
        ),
        vscode.commands.registerCommand(
            'ai-validator.checkLiveTarget',
            () => commands.validateCurrentFile(),
        ),
        vscode.commands.registerCommand(
            'ai-validator.createAirflowConnection',
            () => {
                vscode.window.showInformationMessage(
                    'Airflow connection creation will be available in Phase 3.',
                );
            },
        ),
        vscode.commands.registerCommand(
            'ai-validator.addConnectionProfile',
            () => {
                vscode.commands.executeCommand(
                    'workbench.action.openSettings',
                    'ai-validator.connections',
                );
            },
        ),
    );

    // -------------------------------------------------------------------
    // Register code action provider
    // -------------------------------------------------------------------

    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            { language: 'python', scheme: 'file' },
            codeActions,
            {
                providedCodeActionKinds:
                    ValidatorCodeActionProvider.providedCodeActionKinds,
            },
        ),
    );

    // -------------------------------------------------------------------
    // Auto-validate on save
    // -------------------------------------------------------------------

    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument((document) => {
            if (getValidateOnSave() && document.languageId === 'python') {
                commands.validateCurrentFile();
            }
        }),
    );

    // -------------------------------------------------------------------
    // Auto-validate on open
    // -------------------------------------------------------------------

    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor((editor) => {
            if (
                getValidateOnOpen() &&
                editor?.document.languageId === 'python'
            ) {
                commands.validateCurrentFile();
            }
        }),
    );

    // -------------------------------------------------------------------
    // Register disposables
    // -------------------------------------------------------------------

    context.subscriptions.push(engine, diagnostics, statusBar, commands);

    // Validate the current file if one is open
    if (
        vscode.window.activeTextEditor?.document.languageId === 'python'
    ) {
        commands.validateCurrentFile();
    }
}

export function deactivate(): void {
    engine?.dispose();
    commands?.dispose();
}
