'use strict';

(() => {
  const form = document.querySelector('#repair-form');
  const fields = document.querySelector('#form-fields');
  const submitButton = document.querySelector('#submit-button');
  const refreshButton = document.querySelector('#refresh-button');
  const formMessage = document.querySelector('#form-message');
  const listMessage = document.querySelector('#list-message');
  const list = document.querySelector('#request-list');
  const filterButtons = document.querySelectorAll('#urgency-filters button');
  const filterMessage = document.querySelector('#filter-message');
  let selectedUrgency = '全部';
  let hasLoaded = false;
  let client;
  let submitting = false;
  let loading = false;

  function message(element, text, type = '') {
    element.textContent = text;
    element.className = `message ${type}`;
  }

  // 所有資料以文字節點呈現，避免把使用者輸入當成 HTML 執行。
  function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  // 只篩選已讀取的最近 20 筆，不發出額外資料庫請求。
  function applyUrgencyFilter() {
    let visibleCount = 0;
    for (const card of list.children) {
      card.hidden = selectedUrgency !== '全部' && card.dataset.urgency !== selectedUrgency;
      if (!card.hidden) visibleCount += 1;
    }
    for (const button of filterButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.urgency === selectedUrgency));
    }
    message(filterMessage, hasLoaded && list.childElementCount > 0 && visibleCount === 0
      ? `最近 20 筆中沒有緊急程度為「${selectedUrgency}」的報修。` : '');
  }

  for (const button of filterButtons) {
    button.addEventListener('click', () => {
      selectedUrgency = button.dataset.urgency;
      applyUrgencyFilter();
    });
  }

  function renderRequests(requests) {
    const fragment = document.createDocumentFragment();
    for (const request of requests) {
      const card = document.createElement('article');
      card.className = 'request-card';
      card.dataset.urgency = request.urgency;
      const heading = element('div', '', 'card-heading');
      heading.append(element('h3', `${request.location} · ${request.category}`));
      const badges = element('div', '', 'badges');
      badges.append(element('span', request.status, 'badge'));
      badges.append(element('span', `緊急：${request.urgency}`,
        request.urgency === '高' ? 'badge urgency-high' : 'badge'));
      heading.append(badges);
      const date = new Date(request.created_at);
      const timeText = Number.isNaN(date.getTime()) ? '時間未知' :
        new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
      const meta = element('p', `${request.reporter_name} · `, 'request-meta');
      const time = element('time', timeText);
      if (!Number.isNaN(date.getTime())) time.dateTime = date.toISOString();
      meta.append(time);
      card.append(heading, meta, element('p', request.description, 'request-description'));
      fragment.append(card);
    }
    list.replaceChildren(fragment);
    hasLoaded = true;
    applyUrgencyFilter();
  }

  async function loadRequests() {
    if (loading) return;
    loading = true;
    refreshButton.disabled = true;
    list.setAttribute('aria-busy', 'true');
    message(listMessage, '正在載入清單…');
    try {
      const { data, error } = await client.from('repair_requests')
        .select('id,created_at,reporter_name,location,category,description,urgency,status')
        .order('created_at', { ascending: false }).order('id', { ascending: false }).limit(20);
      if (error) throw error;
      renderRequests(data || []);
      message(listMessage, data?.length ? '' : '目前還沒有報修紀錄，歡迎登記第一筆。');
    } catch (error) {
      message(listMessage, `清單載入失敗，請重新整理再試。${list.childElementCount ? ' 下方仍是上次載入的資料。' : ''}（${error.message || '連線異常'}）`, 'error');
    } finally {
      loading = false;
      refreshButton.disabled = false;
      list.setAttribute('aria-busy', 'false');
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submitting || !client || !form.reportValidity()) return;
    const input = new FormData(form);
    // 白名單只送出可新增的五個欄位；不送 status、id 或 created_at。
    const payload = Object.fromEntries(['reporter_name', 'location', 'category', 'description', 'urgency']
      .map((key) => [key, String(input.get(key) || '').trim()]));
    if (Object.values(payload).some((value) => !value)) {
      message(formMessage, '請完整填寫所有欄位，內容不可只有空白。', 'error');
      return;
    }
    submitting = true;
    fields.disabled = true;
    submitButton.textContent = '送出中…';
    message(formMessage, '正在送出，請稍候…');
    try {
      const { error } = await client.from('repair_requests').insert(payload);
      if (error) throw error;
      form.reset();
      message(formMessage, '報修已成功登記，感謝您的回報。', 'success');
      // 等待既有清單請求完成，再取得包含新增案件的最新清單。
      while (loading) await new Promise((resolve) => setTimeout(resolve, 50));
      await loadRequests();
    } catch (error) {
      message(formMessage, `送出未確認成功，已保留填寫內容。請先重新整理清單確認，避免重複登記。（${error.message || '連線異常'}）`, 'error');
    } finally {
      submitting = false;
      fields.disabled = false;
      submitButton.textContent = '送出報修';
    }
  });

  refreshButton.addEventListener('click', loadRequests);
  try {
    const config = window.REPAIR_CONFIG;
    if (!window.supabase?.createClient || !config?.supabaseUrl ||
        !config?.supabasePublishableKey?.startsWith('sb_publishable_')) {
      throw new Error('連線設定或程式載入失敗，請重新載入頁面。');
    }
    client = window.supabase.createClient(config.supabaseUrl, config.supabasePublishableKey, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      global: { fetch: (url, options = {}) => fetch(url, { ...options, signal: AbortSignal.timeout(15000) }) },
    });
    fields.disabled = false;
    loadRequests();
  } catch (error) {
    message(formMessage, error.message, 'error');
    message(listMessage, '無法連線，請重新載入頁面。', 'error');
    list.setAttribute('aria-busy', 'false');
  }
})();
