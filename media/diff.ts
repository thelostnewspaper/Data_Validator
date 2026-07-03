/**
 * Unified diff renderer for the webview.
 *
 * Parses unified diff format and renders with syntax highlighting:
 * - Additions: green
 * - Deletions: red
 * - Context: grey
 * - Headers: blue
 */

export function renderDiff(diffText: string): string {
    if (!diffText) {
        return '<div class="diff-container"><div class="diff-line context">No changes</div></div>';
    }

    const lines = diffText.split('\n');
    const htmlLines: string[] = [];

    for (const line of lines) {
        const escapedLine = escapeHtml(line);

        if (line.startsWith('+++') || line.startsWith('---')) {
            htmlLines.push(`<div class="diff-line header">${escapedLine}</div>`);
        } else if (line.startsWith('@@')) {
            htmlLines.push(`<div class="diff-line header">${escapedLine}</div>`);
        } else if (line.startsWith('+')) {
            htmlLines.push(`<div class="diff-line addition">${escapedLine}</div>`);
        } else if (line.startsWith('-')) {
            htmlLines.push(`<div class="diff-line deletion">${escapedLine}</div>`);
        } else {
            htmlLines.push(`<div class="diff-line context">${escapedLine}</div>`);
        }
    }

    return `<div class="diff-container">${htmlLines.join('')}</div>`;
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
