import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Locally, /api goes to the FastAPI server. Deployed, CloudFront (serverless) or
// Caddy (single server) sends /api to the backend on the same address.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8002' } },
});
