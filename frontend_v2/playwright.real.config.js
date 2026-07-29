import { defineConfig } from '@playwright/test';


export default defineConfig({
    testDir: './e2e-real',
    fullyParallel: false,
    workers: 1,
    retries: 0,
    reporter: 'line',
    use: {
        baseURL: 'http://127.0.0.1:5173',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
            ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
            : {},
    },
    webServer: [
        {
            command: '../.venv/bin/python e2e/support/real_backend.py',
            url: 'http://127.0.0.1:7100/health/ready',
            reuseExistingServer: false,
            timeout: 120_000,
            env: {
                ...process.env,
                MMG_E2E_BACKEND_PORT: '7100',
            },
        },
        {
            command: 'npm run dev -- --host 127.0.0.1 --port 5173',
            url: 'http://127.0.0.1:5173',
            reuseExistingServer: false,
            timeout: 120_000,
            env: {
                ...process.env,
                VITE_API_URL: 'http://127.0.0.1:7100',
            },
        },
    ],
});
