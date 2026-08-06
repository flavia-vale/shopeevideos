import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000,
    // Em desenvolvimento o front roda na 3000 e o Flask na 10000;
    // o proxy faz /api cair no backend sem precisar de CORS nem URL absoluta.
    proxy: {
      '/api': 'http://localhost:10000'
    }
  }
})