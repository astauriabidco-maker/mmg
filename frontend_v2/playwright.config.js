import { defineConfig } from '@playwright/test';


export default defineConfig({
    testDir: './e2e',
    fullyParallel: false,
    retries: process.env.CI ? 2 : 0,
    reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'line',
    use: {
        baseURL: 'http://127.0.0.1:5173',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
            : {},
    },
    webServer: {
        command: 'npm run dev -- --host 127.0.0.1 --port 5173',
        url: 'http://127.0.0.1:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
    },
});
