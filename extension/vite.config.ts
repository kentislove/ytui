import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 只有側邊欄用 Vite 編譯；manifest 與 YouTube 頁面腳本放在 public/，原樣複製到 dist/。
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist',
    // v1.2：讓 Vite 清空 dist 時，若資料夾被其他程式開著（檔案總管、已載入擴充功能的 Chrome），
    // 編譯工具會當掉（0xC0000409）。改由 package.json 的 prebuild 先刪 dist 內的檔案、保留資料夾本身。
    emptyOutDir: false,
    rollupOptions: { input: { sidepanel: 'sidepanel.html' } },
  },
})
