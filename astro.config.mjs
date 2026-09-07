import { defineConfig } from 'astro/config';

export default defineConfig({
  outDir: 'dist',
  server: { port: 4322 },
  trailingSlash: 'always',
  site: 'https://zbi.mir-betona33.ru',
});
