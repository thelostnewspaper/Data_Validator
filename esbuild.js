// @ts-check
const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');

/** @type {import('esbuild').BuildOptions} */
const extensionConfig = {
    entryPoints: ['src/extension.ts'],
    bundle: true,
    outfile: 'dist/extension.js',
    external: ['vscode'],
    format: 'cjs',
    platform: 'node',
    target: 'node18',
    sourcemap: true,
    minify: false,
};

/** @type {import('esbuild').BuildOptions} */
const webviewConfig = {
    entryPoints: ['media/main.ts'],
    bundle: true,
    outfile: 'media/main.js',
    format: 'iife',
    platform: 'browser',
    target: 'es2020',
    sourcemap: true,
    minify: false,
};

async function build() {
    if (watch) {
        const extCtx = await esbuild.context(extensionConfig);
        const webCtx = await esbuild.context(webviewConfig);
        await extCtx.watch();
        await webCtx.watch();
        console.log('[esbuild] Watching for changes...');
    } else {
        await esbuild.build(extensionConfig);
        await esbuild.build(webviewConfig);
        console.log('[esbuild] Build complete.');
    }
}

build().catch((err) => {
    console.error(err);
    process.exit(1);
});
