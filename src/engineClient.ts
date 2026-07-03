/**
 * Engine client — spawns and manages the Python validation engine.
 *
 * Communicates via JSON-RPC 2.0 over stdio using vscode-jsonrpc.
 * Handles request/response for validation and streaming notifications
 * for AI remediation.
 */

import * as cp from 'child_process';
import * as path from 'path';
import * as vscode from 'vscode';
import {
    createMessageConnection,
    StreamMessageReader,
    StreamMessageWriter,
    MessageConnection,
    RequestType,
    NotificationType,
} from 'vscode-jsonrpc/node';
import {
    Methods,
    ValidationResult,
    ValidateRequest,
    AiRemediateRequest,
    RemediationOption,
    GetPacksResponse,
} from './types';
import { getPythonPath } from './config';

export class EngineClient implements vscode.Disposable {
    private process: cp.ChildProcess | undefined;
    private connection: MessageConnection | undefined;
    private outputChannel: vscode.OutputChannel;
    private restartCount = 0;
    private maxRestarts = 3;
    private disposed = false;

    // Notification handlers
    private remediationStreamHandlers: ((option: RemediationOption) => void)[] = [];
    private remediationDoneHandlers: (() => void)[] = [];
    private remediationErrorHandlers: ((message: string) => void)[] = [];

    constructor(private readonly extensionPath: string) {
        this.outputChannel = vscode.window.createOutputChannel('AI Validator Engine');
    }

    /**
     * Start the Python engine child process and establish JSON-RPC connection.
     */
    async start(): Promise<void> {
        if (this.connection) {
            return; // Already running
        }

        const pythonPath = getPythonPath();
        const serverScript = path.join(this.extensionPath, 'engine', 'server.py');

        this.outputChannel.appendLine(
            `Starting engine: ${pythonPath} -u ${serverScript}`,
        );

        try {
            this.process = cp.spawn(pythonPath, ['-u', serverScript], {
                cwd: this.extensionPath,
                env: {
                    ...process.env,
                    PYTHONUNBUFFERED: '1',
                    PYTHONPATH: this.extensionPath,
                },
            });

            if (!this.process.stdout || !this.process.stdin) {
                throw new Error('Failed to get stdio streams from engine process');
            }

            // Log stderr (engine debug output)
            this.process.stderr?.on('data', (data: Buffer) => {
                this.outputChannel.appendLine(`[engine] ${data.toString().trim()}`);
            });

            // Handle process exit
            this.process.on('exit', (code, signal) => {
                this.outputChannel.appendLine(
                    `Engine exited: code=${code}, signal=${signal}`,
                );
                this.connection = undefined;
                this.process = undefined;

                if (!this.disposed && this.restartCount < this.maxRestarts) {
                    this.restartCount++;
                    const delay = Math.min(1000 * Math.pow(2, this.restartCount), 10000);
                    this.outputChannel.appendLine(
                        `Restarting in ${delay}ms (attempt ${this.restartCount}/${this.maxRestarts})`,
                    );
                    setTimeout(() => this.start(), delay);
                }
            });

            // Create JSON-RPC connection
            this.connection = createMessageConnection(
                new StreamMessageReader(this.process.stdout),
                new StreamMessageWriter(this.process.stdin),
            );

            // Register notification handlers
            this.connection.onNotification(
                new NotificationType<RemediationOption>(Methods.AI_REMEDIATE_STREAM),
                (option) => {
                    this.remediationStreamHandlers.forEach((h) => h(option));
                },
            );

            this.connection.onNotification(
                new NotificationType<{ status: string }>(Methods.AI_REMEDIATE_DONE),
                () => {
                    this.remediationDoneHandlers.forEach((h) => h());
                },
            );

            this.connection.onNotification(
                new NotificationType<{ message: string }>(Methods.AI_REMEDIATE_ERROR),
                (params) => {
                    this.remediationErrorHandlers.forEach((h) => h(params.message));
                },
            );

            this.connection.listen();
            this.restartCount = 0;
            this.outputChannel.appendLine('Engine connection established');
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.outputChannel.appendLine(`Failed to start engine: ${msg}`);
            vscode.window.showErrorMessage(
                'AI Validator: Failed to start engine. Check the Output panel for details.',
            );
        }
    }

    /**
     * Send a validate request to the engine.
     */
    async validate(request: ValidateRequest): Promise<ValidationResult | undefined> {
        if (!this.connection) {
            await this.start();
        }
        if (!this.connection) {
            return undefined;
        }

        try {
            const requestType = new RequestType<ValidateRequest, ValidationResult, void>(
                Methods.VALIDATE,
            );
            return await this.connection.sendRequest(requestType, request);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.outputChannel.appendLine(`Validate error: ${msg}`);
            return undefined;
        }
    }

    /**
     * Send an AI remediation request (streaming).
     */
    async aiRemediate(request: AiRemediateRequest): Promise<void> {
        if (!this.connection) {
            await this.start();
        }
        if (!this.connection) {
            return;
        }

        try {
            const requestType = new RequestType<AiRemediateRequest, { status: string }, void>(
                Methods.AI_REMEDIATE,
            );
            await this.connection.sendRequest(requestType, request);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.outputChannel.appendLine(`AI remediate error: ${msg}`);
            this.remediationErrorHandlers.forEach((h) => h(msg));
        }
    }

    /**
     * Get the list of available packs.
     */
    async getPacks(): Promise<GetPacksResponse | undefined> {
        if (!this.connection) {
            await this.start();
        }
        if (!this.connection) {
            return undefined;
        }

        try {
            const requestType = new RequestType<Record<string, never>, GetPacksResponse, void>(
                Methods.GET_PACKS,
            );
            return await this.connection.sendRequest(requestType, {});
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.outputChannel.appendLine(`Get packs error: ${msg}`);
            return undefined;
        }
    }

    // -------------------------------------------------------------------
    // Streaming notification registration
    // -------------------------------------------------------------------

    onRemediationStream(handler: (option: RemediationOption) => void): void {
        this.remediationStreamHandlers.push(handler);
    }

    onRemediationDone(handler: () => void): void {
        this.remediationDoneHandlers.push(handler);
    }

    onRemediationError(handler: (message: string) => void): void {
        this.remediationErrorHandlers.push(handler);
    }

    // -------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------

    async stop(): Promise<void> {
        if (this.connection) {
            try {
                const requestType = new RequestType<Record<string, never>, { status: string }, void>(
                    Methods.SHUTDOWN,
                );
                await this.connection.sendRequest(requestType, {});
            } catch {
                // Ignore shutdown errors
            }
            this.connection.dispose();
            this.connection = undefined;
        }

        if (this.process) {
            this.process.kill();
            this.process = undefined;
        }
    }

    dispose(): void {
        this.disposed = true;
        this.stop();
        this.outputChannel.dispose();
    }
}
