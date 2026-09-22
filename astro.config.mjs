import { defineConfig } from 'astro/config';

export default defineConfig({
  outDir: 'dist',
  server: { port: 4322 },
  trailingSlash: 'always',
  site: 'https://zhbi.mir-betona33.ru',
});
