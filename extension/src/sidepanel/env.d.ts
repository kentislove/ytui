/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
// 不額外安裝 @types/chrome，MVP 階段直接宣告。
declare const chrome: any
