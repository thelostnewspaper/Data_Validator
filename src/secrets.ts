/**
 * SecretStorage wrapper — manages sensitive credentials.
 *
 * Uses VS Code's SecretStorage API (OS keychain backed).
 * NEVER logs, surfaces, or stores secrets in settings.json.
 */

import * as vscode from 'vscode';

const KEY_PREFIX = 'ai-validator';

export class SecretManager {
    constructor(private readonly secretStorage: vscode.SecretStorage) {}

    // -------------------------------------------------------------------
    // AI Provider API keys
    // -------------------------------------------------------------------

    async storeApiKey(provider: string, key: string): Promise<void> {
        await this.secretStorage.store(`${KEY_PREFIX}.apiKey.${provider}`, key);
    }

    async getApiKey(provider: string): Promise<string | undefined> {
        return this.secretStorage.get(`${KEY_PREFIX}.apiKey.${provider}`);
    }

    async deleteApiKey(provider: string): Promise<void> {
        await this.secretStorage.delete(`${KEY_PREFIX}.apiKey.${provider}`);
    }

    // -------------------------------------------------------------------
    // Connection profile passwords
    // -------------------------------------------------------------------

    async storeConnectionPassword(profileName: string, password: string): Promise<void> {
        await this.secretStorage.store(
            `${KEY_PREFIX}.connection.${profileName}`,
            password,
        );
    }

    async getConnectionPassword(profileName: string): Promise<string | undefined> {
        return this.secretStorage.get(`${KEY_PREFIX}.connection.${profileName}`);
    }

    async deleteConnectionPassword(profileName: string): Promise<void> {
        await this.secretStorage.delete(`${KEY_PREFIX}.connection.${profileName}`);
    }

    // -------------------------------------------------------------------
    // Interactive setup
    // -------------------------------------------------------------------

    /**
     * Prompt the user to enter an API key with a masked input box.
     */
    async promptForApiKey(provider: string): Promise<string | undefined> {
        const key = await vscode.window.showInputBox({
            title: `Enter ${provider} API Key`,
            prompt: 'Your API key will be stored securely in the OS keychain.',
            password: true,
            placeHolder: 'sk-...',
            ignoreFocusOut: true,
        });

        if (key) {
            await this.storeApiKey(provider, key);
            vscode.window.showInformationMessage(
                `${provider} API key saved securely.`,
            );
        }

        return key;
    }

    /**
     * Prompt the user to enter a connection password.
     */
    async promptForConnectionPassword(
        profileName: string,
    ): Promise<string | undefined> {
        const password = await vscode.window.showInputBox({
            title: `Password for connection '${profileName}'`,
            prompt: 'Stored securely in the OS keychain.',
            password: true,
            ignoreFocusOut: true,
        });

        if (password) {
            await this.storeConnectionPassword(profileName, password);
        }

        return password;
    }
}
