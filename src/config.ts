/**
 * Configuration reader — reads VS Code settings for the extension.
 */

import * as vscode from 'vscode';

const SECTION = 'ai-validator';

export interface ConnectionProfile {
    name: string;
    type: 'doris' | 'bigquery' | 'snowflake' | 'airflow';
    host: string;
    port?: number;
    database?: string;
    username?: string;
}

export function getPythonPath(): string {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<string>('pythonPath', 'python3');
}

export function getEnabledPacks(): string[] {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<string[]>('enabledPacks', ['airflow-universal']);
}

export function getValidateOnSave(): boolean {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<boolean>('validateOnSave', true);
}

export function getValidateOnOpen(): boolean {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<boolean>('validateOnOpen', true);
}

export function getAiProvider(): string {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<string>('ai.provider', 'claude');
}

export function getAiModel(): string {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<string>('ai.model', '');
}

export function getCheapModel(): string {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<string>('ai.cheapModel', '');
}

export function getConnections(): ConnectionProfile[] {
    return vscode.workspace
        .getConfiguration(SECTION)
        .get<ConnectionProfile[]>('connections', []);
}
