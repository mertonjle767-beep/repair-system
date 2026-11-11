'use strict';
(() => {
  const status = document.querySelector('#connection-status');
  const button = document.querySelector('#install-button');
  const help = document.querySelector('#install-help');
  const message = document.querySelector('#pwa-message');
  let prompt;
  function updateConnection() {
    status.textContent = navigator.onLine
      ? '已連上網路；報修與清單仍需伺服器連線成功。'
      : '目前離線：可開啟介面，無法送出或讀取最新清單。填寫內容只留在此頁，關閉或重新載入會遺失。';
  }
  updateConnection();
  window.addEventListener('online', updateConnection);
  window.addEventListener('offline', updateConnection);
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); prompt = event; button.hidden = false;
  });
  button.addEventListener('click', async () => {
    if (!prompt) return;
    const current = prompt; prompt = null; button.hidden = true;
    await current.prompt(); await current.userChoice;
  });
  function installed() {
    button.hidden = true; help.hidden = true; prompt = null;
  }
  window.addEventListener('appinstalled', installed);
  if (window.matchMedia('(display-mode: standalone)').matches || navigator.standalone) installed();
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('./sw.js').then(registration => {
      const notify = () => { message.textContent = '有新版本；請先完成或複製填寫內容，再關閉所有報修系統視窗並重新開啟。'; };
      if (registration.waiting) notify();
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        worker?.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) notify();
        });
      });
    }).catch(() => {
      message.textContent = '離線功能尚未準備完成，請連線後重新開啟；目前仍可使用網頁。';
    });
  } else {
    message.textContent = '此環境不支援離線安裝，請使用 HTTPS 或 localhost 的新版瀏覽器。';
  }
})();
