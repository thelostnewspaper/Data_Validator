/**
 * Code actions — maps SuggestedFix[] → lightbulb Quick Fixes.
 *
 * For each SuggestedFix with confidence >= 0.80, creates a CodeAction
 * with a WorkspaceEdit that applies the rename/removal.
 */

import * as vscode from 'vscode';
import { SuggestedFix } from './types';

export class ValidatorCodeActionProvider implements vscode.CodeActionProvider {
    public static readonly providedCodeActionKinds = [
        vscode.CodeActionKind.QuickFix,
    ];

    private fixesMap = new Map<string, SuggestedFix[]>();

    /**
     * Update the available fixes for a file.
     */
    updateFixes(uri: vscode.Uri, fixes: SuggestedFix[]): void {
        this.fixesMap.set(uri.toString(), fixes);
    }

    /**
     * Clear fixes for a file.
     */
    clearFixes(uri: vscode.Uri): void {
        this.fixesMap.delete(uri.toString());
    }

    provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range | vscode.Selection,
        _context: vscode.CodeActionContext,
        _token: vscode.CancellationToken,
    ): vscode.CodeAction[] {
        const fixes = this.fixesMap.get(document.uri.toString());
        if (!fixes || fixes.length === 0) {
            return [];
        }

        const actions: vscode.CodeAction[] = [];

        for (const fix of fixes) {
            // Only offer fixes with >= 0.80 confidence
            if (fix.confidence < 0.80) {
                continue;
            }

            // Check if the fix's line is within the range the user is looking at
            const fixLine = Math.max(0, (fix.line || 1) - 1);
            if (fixLine < range.start.line - 2 || fixLine > range.end.line + 2) {
                continue;
            }

            const action = new vscode.CodeAction(
                `AI Validator: ${fix.description}`,
                vscode.CodeActionKind.QuickFix,
            );

            action.diagnostics = _context.diagnostics.filter(
                (d) => d.code === fix.check_id,
            );

            // Create the workspace edit
            if (fix.old_text && fix.new_text) {
                action.edit = new vscode.WorkspaceEdit();

                // Find the old text in the document and replace it
                const text = document.getText();
                const index = text.indexOf(fix.old_text);

                if (index >= 0) {
                    const startPos = document.positionAt(index);
                    const endPos = document.positionAt(index + fix.old_text.length);
                    action.edit.replace(
                        document.uri,
                        new vscode.Range(startPos, endPos),
                        fix.new_text,
                    );
                }
            }

            // Show confidence in the title
            const pct = Math.round(fix.confidence * 100);
            action.title = `AI Validator: ${fix.description} (${pct}% match)`;
            action.isPreferred = fix.confidence >= 0.95;

            actions.push(action);
        }

        return actions;
    }
}
