const status = document.getElementById('status')
navigator.mediaDevices.getUserMedia({ audio: true })
  .then((stream) => {
    stream.getTracks().forEach((t) => t.stop())
    status.className = 'ok'
    status.textContent = '授權成功！可以關閉這個分頁，回到側邊欄按「按一下說話」。 / Done. You can close this tab.'
  })
  .catch((e) => {
    status.className = 'bad'
    status.textContent = '授權失敗：' + e.message + '。請在網址列左側的鎖頭圖示中允許麥克風。'
  })
