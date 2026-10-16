// 點擴充功能圖示時打開側邊欄。
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
})
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
