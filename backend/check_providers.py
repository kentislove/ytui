"""檢查三家 API 金鑰能不能用、抓到哪些模型（不會印出金鑰）。用法：.venv\\Scripts\\python.exe check_providers.py"""
import ai_router as R

keys = R.load_keys()
print("讀到的金鑰：", "、".join(k.replace("_API_KEY", "") for k in keys) or "（沒有）")
for k, v in keys.items():
    print(f"  {k.replace('_API_KEY', '')}：長度 {len(v)}，開頭 {v[:4]}…")

cands = R.discover(keys)
for p in ("gemini", "groq", "openrouter"):
    vis = [c.model for c in cands if c.provider == p and c.vision]
    txt = [c.model for c in cands if c.provider == p and not c.vision]
    print(f"\n【{p}】看圖 {len(vis)} 個、只能文字 {len(txt)} 個")
    for m in vis:
        print(f"  🖼 {m}" + ("（可免費查網路）" if p == "gemini" and R.gemini_can_search(m) else ""))
    for m in txt[:12]:
        print(f"  📝 {m}")
    if len(txt) > 12:
        print(f"  …另有 {len(txt) - 12} 個文字模型")

# 每家用最簡單的一句話試一次，確認金鑰真的能用
print("\n【實際呼叫測試】（每家只問一句「你好」，不附圖）")
seen = set()
for c in cands:
    if c.provider in seen:
        continue
    try:
        ans, tin, tout = R.call(c, keys, "用繁體中文回答，10 個字以內。", "你好", [], False, 30)
        print(f"  ✅ {c.provider}:{c.model} → {ans.strip()[:30]}")
        seen.add(c.provider)
    except R.CallError as e:
        print(f"  ❌ {c.provider}:{c.model} → {e.status} {e.detail[:120]}")
