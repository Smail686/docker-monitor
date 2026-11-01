/* Docker Monitor - Telegram Mini App frontend (vanilla JS, no build step).
 *
 * Security note: all dynamic text is inserted with textContent / text nodes, never
 * innerHTML, so container names, images and log lines cannot inject markup.
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------------- //
  // Telegram bridge and language
  // ------------------------------------------------------------------------- //
  const tg = (window.Telegram && window.Telegram.WebApp) || null;
  const INIT = tg ? (tg.initData || '') : '';
  const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  const LANG = String((tgUser && tgUser.language_code) || navigator.language || 'en')
    .toLowerCase().startsWith('ru') ? 'ru' : 'en';

  const I18N = {
    en: {
      tab_containers: 'Containers', tab_history: 'History', tab_settings: 'Settings', tab_system: 'Server',
      sys_cpu: 'Processor', sys_ram: 'Memory', sys_swap: 'Swap', sys_disk: 'Disk', sys_load: 'Load average',
      sys_temp: 'Temperature', sys_uptime: 'Uptime', sys_cores: 'Cores', sys_os: 'System', sys_kernel: 'Kernel',
      sys_host: 'Host', sys_containers: 'Containers', sys_running: '{r} of {n} running',
      search: 'Search containers…', refresh: 'Refresh',
      f_all: 'All', f_problems: 'Problems', f_running: 'Running', f_stopped: 'Stopped',
      no_containers: 'No containers found',
      st_running: 'running', st_exited: 'stopped', st_unhealthy: 'unhealthy', st_restarting: 'restarting',
      st_paused: 'paused', st_created: 'created', st_dead: 'dead', st_unknown: 'unknown',
      up: 'Up {d}', stopped_ago: 'Stopped {d} ago', ago: '{d} ago', just_now: 'just now',
      u_d: 'd', u_h: 'h', u_m: 'm', u_s: 's',
      start: 'Start', stop: 'Stop', restart: 'Restart',
      confirm_start: 'Start {name}?', confirm_stop: 'Stop {name}?', confirm_restart: 'Restart {name}?',
      done: 'Done', cancel: 'Cancel', close: 'Close',
      logs: 'Logs', copy: 'Copy', copied: 'Copied', no_logs: 'No log output', lines: '{n} lines',
      cpu: 'CPU', ram: 'Memory',
      mute: '🔕 Mute alerts', unmute: '🔔 Unmute', mute_for: 'Mute alerts for',
      muted_until: 'Alerts muted until {t}',
      m15: '15 minutes', m30: '30 minutes', h1: '1 hour', h4: '4 hours', h8: '8 hours', h24: '24 hours',
      image: 'Image', id: 'ID', restarts: 'Restarts', exit_code: 'Exit code', oom: 'Out of memory',
      ports: 'Ports', health: 'Health check', started: 'Started', finished: 'Stopped',
      protected: 'Protected container: controls are disabled.',
      read_only: 'You have read-only access.',
      f24: 'last 24 h', f7: 'last 7 days', ftotal: 'total',
      top_title: 'Most frequent (7 days)', no_failures: 'No failures recorded 🎉',
      load_more: 'Load more', all_containers: 'All',
      maint: 'Maintenance mode', maint_desc: 'Pause alerts for every container. Failures are still recorded.',
      maint_on: 'Alerts paused until {t}', maint_enable: 'Enable…', maint_disable: 'Disable',
      muted_list: 'Muted containers', no_mutes: 'Nothing is muted', action_log: 'Action log',
      no_actions: 'No actions yet', account: 'Account', role_admin: 'Administrator', role_viewer: 'Read-only',
      err_docker: 'Docker is not reachable.', err_expired: 'Session expired. Close and reopen the app.',
      err_open: 'Please open this app from Telegram.',
      err_forbidden: 'Access denied. Your Telegram ID is shown below; ask the owner to add it to ADMIN_TELEGRAM_IDS.',
      err_network: 'No connection to the server', err_busy: 'Another action is already running',
      err_protected: 'This container is protected', err_gone: 'Container no longer exists',
      err_generic: 'Something went wrong',
    },
    ru: {
      tab_containers: 'Контейнеры', tab_history: 'История', tab_settings: 'Настройки', tab_system: 'Сервер',
      sys_cpu: 'Процессор', sys_ram: 'Память', sys_swap: 'Подкачка', sys_disk: 'Диск', sys_load: 'Нагрузка (load average)',
      sys_temp: 'Температура', sys_uptime: 'Аптайм', sys_cores: 'Ядер', sys_os: 'Система', sys_kernel: 'Ядро',
      sys_host: 'Хост', sys_containers: 'Контейнеры', sys_running: 'работает {r} из {n}',
      search: 'Поиск контейнеров…', refresh: 'Обновить',
      f_all: 'Все', f_problems: 'Проблемы', f_running: 'Работают', f_stopped: 'Остановлены',
      no_containers: 'Контейнеры не найдены',
      st_running: 'работает', st_exited: 'остановлен', st_unhealthy: 'unhealthy', st_restarting: 'перезапуск',
      st_paused: 'пауза', st_created: 'создан', st_dead: 'dead', st_unknown: 'неизвестно',
      up: 'Работает {d}', stopped_ago: 'Остановлен {d} назад', ago: '{d} назад', just_now: 'только что',
      u_d: 'д', u_h: 'ч', u_m: 'мин', u_s: 'с',
      start: 'Запустить', stop: 'Остановить', restart: 'Перезапустить',
      confirm_start: 'Запустить {name}?', confirm_stop: 'Остановить {name}?', confirm_restart: 'Перезапустить {name}?',
      done: 'Готово', cancel: 'Отмена', close: 'Закрыть',
      logs: 'Логи', copy: 'Копировать', copied: 'Скопировано', no_logs: 'Логов нет', lines: '{n} строк',
      cpu: 'CPU', ram: 'Память',
      mute: '🔕 Отключить уведомления', unmute: '🔔 Включить уведомления', mute_for: 'Отключить уведомления на',
      muted_until: 'Уведомления отключены до {t}',
      m15: '15 минут', m30: '30 минут', h1: '1 час', h4: '4 часа', h8: '8 часов', h24: '24 часа',
      image: 'Образ', id: 'ID', restarts: 'Перезапусков', exit_code: 'Код выхода', oom: 'Нехватка памяти',
      ports: 'Порты', health: 'Проверка здоровья', started: 'Запущен', finished: 'Остановлен',
      protected: 'Защищённый контейнер: управление отключено.',
      read_only: 'У вас доступ только для просмотра.',
      f24: 'за 24 ч', f7: 'за 7 дней', ftotal: 'всего',
      top_title: 'Чаще всего (7 дней)', no_failures: 'Сбоев пока нет 🎉',
      load_more: 'Загрузить ещё', all_containers: 'Все',
      maint: 'Режим обслуживания', maint_desc: 'Приостановить уведомления для всех контейнеров. Сбои всё равно записываются.',
      maint_on: 'Уведомления приостановлены до {t}', maint_enable: 'Включить…', maint_disable: 'Выключить',
      muted_list: 'Отключённые уведомления', no_mutes: 'Ничего не отключено', action_log: 'Журнал действий',
      no_actions: 'Действий пока нет', account: 'Аккаунт', role_admin: 'Администратор', role_viewer: 'Только просмотр',
      err_docker: 'Docker недоступен.', err_expired: 'Сессия истекла. Закройте и откройте приложение заново.',
      err_open: 'Откройте это приложение из Telegram.',
      err_forbidden: 'Нет доступа. Ваш Telegram ID указан ниже, передайте его владельцу, чтобы он добавил его в ADMIN_TELEGRAM_IDS.',
      err_network: 'Нет связи с сервером', err_busy: 'Другое действие уже выполняется',
      err_protected: 'Этот контейнер защищён', err_gone: 'Контейнера больше нет',
      err_generic: 'Что-то пошло не так',
    },
  };

  function t(key, vars) {
    let s = (I18N[LANG] && I18N[LANG][key]) || I18N.en[key] || key;
    if (vars) for (const k in vars) s = s.split('{' + k + '}').join(String(vars[k]));
    return s;
  }

  // ------------------------------------------------------------------------- //
  // Small helpers
  // ------------------------------------------------------------------------- //
  /** Tiny hyperscript helper: h('div', {class: 'x', onclick: fn}, child, 'text', ...). */
  function h(tag, props) {
    const el = document.createElement(tag);
    for (const k in (props || {})) {
      const v = props[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    // Children may be nodes, strings, or (nested) arrays of them.
    const kids = [].slice.call(arguments, 2).flat(Infinity);
    for (const kid of kids) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(typeof kid === 'object' ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  const toDate = (iso) => { const d = iso ? new Date(iso) : null; return d && !isNaN(d) ? d : null; };

  function fmtDuration(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    const d = Math.floor(s / 86400), hh = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d) return d + t('u_d') + ' ' + hh + t('u_h');
    if (hh) return hh + t('u_h') + ' ' + m + t('u_m');
    if (m) return m + t('u_m');
    return s + t('u_s');
  }

  function fmtDateTime(iso) {
    const d = toDate(iso);
    if (!d) return '';
    try {
      return d.toLocaleString(LANG === 'ru' ? 'ru-RU' : 'en-GB',
        { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch (e) { return d.toISOString(); }
  }

  function fmtClock(iso) {
    const d = toDate(iso);
    if (!d) return '';
    try { return d.toLocaleTimeString(LANG === 'ru' ? 'ru-RU' : 'en-GB', { hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return ''; }
  }

  function fmtDay(iso) {
    const d = toDate(iso);
    if (!d) return '';
    try { return d.toLocaleDateString(LANG === 'ru' ? 'ru-RU' : 'en-GB', { day: 'numeric', month: 'long' }); }
    catch (e) { return d.toDateString(); }
  }

  function fmtBytes(n) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0, v = n || 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return (i ? v.toFixed(1) : String(Math.round(v))) + ' ' + units[i];
  }

  const haptic = (kind) => { try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* optional */ } };

  let toastEl = null, toastTimer = null;
  function toast(message) {
    if (!toastEl) { toastEl = h('div', { class: 'toast' }); document.body.append(toastEl); }
    toastEl.textContent = message;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2500);
  }

  function confirmDialog(message) {
    return new Promise((resolve) => {
      if (tg && tg.showConfirm && tg.isVersionAtLeast && tg.isVersionAtLeast('6.2')) tg.showConfirm(message, resolve);
      else resolve(window.confirm(message));
    });
  }

  /** Bottom sheet with a list of options; resolves with the chosen value or null. */
  function sheet(title, options) {
    return new Promise((resolve) => {
      let overlay = null;
      const close = (value) => { overlay.remove(); resolve(value); };
      overlay = h('div', { class: 'overlay', onclick: (e) => { if (e.target === overlay) close(null); } },
        h('div', { class: 'sheet' },
          h('h3', {}, title),
          options.map((o) => h('button', { class: 'btn secondary', onclick: () => close(o.value) }, o.label)),
          h('button', { class: 'btn secondary', onclick: () => close(null) }, t('cancel'))));
      document.body.append(overlay);
    });
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); toast(t('copied')); return; } catch (e) { /* fall back below */ }
    try {
      const area = h('textarea', {}); area.value = text; document.body.append(area);
      area.select(); document.execCommand('copy'); area.remove(); toast(t('copied'));
    } catch (e) { toast(t('err_generic')); }
  }

  // ------------------------------------------------------------------------- //
  // API
  // ------------------------------------------------------------------------- //
  async function api(path, opts) {
    opts = opts || {};
    let res;
    try {
      res = await fetch(path, {
        method: opts.method || 'GET',
        headers: { 'X-Telegram-Init-Data': INIT, 'Content-Type': 'application/json' },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    } catch (e) { const err = new Error('network'); err.status = 0; throw err; }
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
    if (!res.ok) {
      const err = new Error((data && data.error) || res.statusText);
      err.status = res.status; err.code = data && data.error; err.data = data || {};
      throw err;
    }
    return data;
  }

  // ------------------------------------------------------------------------- //
  // State
  // ------------------------------------------------------------------------- //
  const root = document.getElementById('app');
  const S = {
    me: null, view: 'list', cname: null, fatal: false,
    containers: [], mutes: [], maintenance: null, loaded: false, dockerDown: false,
    filter: 'all', q: '',
    extra: null, logs: '', tail: 100, busy: false,
    fail: null, failFilter: '', actions: null,
  };
  const V = {};            // cached view containers (so e.g. the search box keeps its text)
  let shell = null;

  const canWrite = () => S.me && S.me.role === 'admin';
  const currentContainer = () => S.containers.find((c) => c.name === S.cname) || null;
  const isMuted = (name) => !!S.maintenance || S.mutes.some((m) => m.container_name === name);

  function statusInfo(c) {
    const s = c.status;
    if (s === 'unhealthy' || s === 'dead') return { cls: 'bad', key: 'st_' + s };
    if (s === 'running') return { cls: c.health === 'starting' ? 'warn' : 'ok', key: 'st_running' };
    if (s === 'restarting' || s === 'paused') return { cls: 'warn', key: 'st_' + s };
    if (s === 'exited') return { cls: (c.exit_code !== 0 || c.oom_killed) ? 'bad' : 'idle', key: 'st_exited' };
    return { cls: 'idle', key: I18N.en['st_' + s] ? 'st_' + s : 'st_unknown' };
  }
  const RANK = { bad: 0, warn: 1, ok: 2, idle: 3 };
  const isProblem = (c) => ['bad', 'warn'].includes(statusInfo(c).cls);
  const FILTERS = {
    all: () => true,
    problems: isProblem,
    running: (c) => c.status === 'running',
    stopped: (c) => c.status === 'exited' || c.status === 'created',
  };

  function uptimeText(c) {
    if (c.status === 'running' && toDate(c.started_at)) return t('up', { d: fmtDuration(Date.now() - toDate(c.started_at)) });
    if (c.status === 'exited' && toDate(c.finished_at)) return t('stopped_ago', { d: fmtDuration(Date.now() - toDate(c.finished_at)) });
    return '';
  }

  // ------------------------------------------------------------------------- //
  // Errors
  // ------------------------------------------------------------------------- //
  function fatal(message, id) {
    S.fatal = true;
    root.replaceChildren(h('div', { class: 'fatal' },
      h('h2', {}, 'Docker Monitor'), h('p', {}, message),
      id ? h('p', {}, h('code', {}, String(id))) : null,
      tg && tg.close ? h('button', { class: 'btn', onclick: () => tg.close() }, t('close')) : null));
  }

  function handleError(e) {
    if (e.status === 401) return fatal(t(e.code === 'expired' ? 'err_expired' : 'err_open'));
    if (e.status === 403 && e.code === 'forbidden') return fatal(t('err_forbidden'), e.data.user_id);
    if (e.status === 503) { S.dockerDown = true; return afterData(); }
    const known = { busy: 'err_busy', protected: 'err_protected', container_not_found: 'err_gone', read_only: 'read_only' };
    if (e.status === 0) return toast(t('err_network'));
    if (e.code === 'docker_error' && e.data.message) return toast(e.data.message);
    toast(t(known[e.code] || 'err_generic'));
  }

  // ------------------------------------------------------------------------- //
  // Data loading
  // ------------------------------------------------------------------------- //
  async function loadContainers() {
    try {
      const data = await api('/api/containers');
      S.dockerDown = false; S.loaded = true;
      S.containers = data.containers; S.mutes = data.mutes; S.maintenance = data.maintenance;
      afterData();
    } catch (e) { handleError(e); }
  }

  function afterData() {
    if (S.fatal) return;
    if (S.view === 'list') updateList();
    else if (S.view === 'detail') updateDetail();
    else if (S.view === 'settings') renderSettings();
  }

  async function loadExtra() {
    const c = currentContainer();
    if (!c) return;
    try { S.extra = (await api('/api/containers/' + c.id)).container; updateDetail(); } catch (e) { handleError(e); }
  }

  async function loadLogs() {
    const c = currentContainer();
    if (!c || !V.detail) return;
    try {
      const r = await api('/api/containers/' + c.id + '/logs?tail=' + S.tail);
      S.logs = r.logs;
      V.detail.pre.textContent = S.logs || t('no_logs');
      V.detail.pre.scrollTop = V.detail.pre.scrollHeight;   // newest lines at the bottom
    } catch (e) { handleError(e); }
  }

  async function loadStats() {
    const c = currentContainer();
    if (!c || !V.detail) return;
    try {
      const r = await api('/api/containers/' + c.id + '/stats');
      const meter = (pct) => h('div', { class: 'meter' }, h('span', { style: 'width:' + Math.min(100, pct) + '%' }));
      V.detail.stats.replaceChildren(...(r.available ? [h('div', { class: 'card' },
        h('div', { class: 'row' }, h('div', { class: 'grow' }, t('cpu')), h('b', {}, r.cpu_percent + '%')), meter(r.cpu_percent),
        h('div', { class: 'row', style: 'margin-top:10px' }, h('div', { class: 'grow' }, t('ram')),
          h('b', {}, fmtBytes(r.mem_used) + (r.mem_limit ? ' / ' + fmtBytes(r.mem_limit) : ''))), meter(r.mem_percent))] : []));
    } catch (e) { /* stats are optional; ignore errors */ }
  }

  async function loadHistory(append) {
    const params = new URLSearchParams({ limit: '30' });
    if (S.failFilter) params.set('container', S.failFilter);
    if (append && S.fail && S.fail.items.length) params.set('before', String(S.fail.items[S.fail.items.length - 1].id));
    try {
      const r = await api('/api/failures?' + params.toString());
      if (append && S.fail) { S.fail.items = S.fail.items.concat(r.items); S.fail.has_more = r.has_more; }
      else S.fail = r;
      renderHistory();
    } catch (e) { handleError(e); }
  }

  async function loadSettings() {
    try { S.actions = (await api('/api/actions?limit=20')).items; } catch (e) { handleError(e); }
    renderSettings();
  }

  // ------------------------------------------------------------------------- //
  // Actions
  // ------------------------------------------------------------------------- //
  async function doAction(c, action) {
    if (S.busy) return;
    if (!(await confirmDialog(t('confirm_' + action, { name: c.name })))) return;
    S.busy = true; updateDetail();
    try {
      await api('/api/containers/' + c.id + '/action', { method: 'POST', body: { action } });
      haptic('success'); toast(t('done'));
      await loadContainers(); loadExtra(); loadLogs(); loadStats();
    } catch (e) { haptic('error'); handleError(e); }
    finally { S.busy = false; if (!S.fatal) updateDetail(); }
  }

  async function postMute(name, minutes) {
    try {
      await api('/api/mutes', { method: 'POST', body: { container_name: name, minutes } });
      haptic('success'); toast(t('done')); await loadContainers();
    } catch (e) { handleError(e); }
  }

  async function postUnmute(name) {
    try {
      await api('/api/mutes/delete', { method: 'POST', body: { container_name: name } });
      haptic('success'); toast(t('done')); await loadContainers();
    } catch (e) { handleError(e); }
  }

  async function chooseMute(name, options) {
    const minutes = await sheet(t('mute_for'), options);
    if (minutes) postMute(name, minutes);
  }
  const MUTE_CONTAINER = () => [
    { label: t('m15'), value: 15 }, { label: t('h1'), value: 60 }, { label: t('h8'), value: 480 }, { label: t('h24'), value: 1440 }];
  const MUTE_ALL = () => [
    { label: t('m30'), value: 30 }, { label: t('h1'), value: 60 }, { label: t('h4'), value: 240 }, { label: t('h24'), value: 1440 }];

  // ------------------------------------------------------------------------- //
  // Views
  // ------------------------------------------------------------------------- //
  function containerCard(c) {
    const si = statusInfo(c), up = uptimeText(c);
    return h('div', { class: 'card tap', onclick: () => go('detail', c.name) },
      h('div', { class: 'row' },
        h('span', { class: 'dot ' + si.cls }),
        h('div', { class: 'grow' }, h('div', { class: 'name' }, c.name), h('div', { class: 'sub' }, c.image + (up ? ' · ' + up : ''))),
        isMuted(c.name) ? h('span', {}, '🔕') : null,
        h('span', { class: 'badge ' + si.cls }, t(si.key))));
  }

  function ensureList() {
    if (V.list) return V.list;
    const search = h('input', { class: 'search', type: 'search', placeholder: t('search'),
      oninput: () => { S.q = search.value.trim().toLowerCase(); updateList(); } });
    const L = { search, banner: h('div'), chips: h('div', { class: 'chips' }), items: h('div') };
    L.root = h('div', {}, L.banner, search, L.chips, L.items);
    return (V.list = L);
  }

  function maintenanceBanner() {
    return S.maintenance ? [h('div', { class: 'banner info' }, t('maint_on', { t: fmtDateTime(S.maintenance.until) }))] : [];
  }

  function updateList() {
    const L = ensureList();
    L.banner.replaceChildren(...(S.dockerDown ? [h('div', { class: 'banner' }, t('err_docker'))] : []), ...maintenanceBanner());
    L.chips.replaceChildren(...Object.keys(FILTERS).map((f) =>
      h('button', { class: 'chip' + (S.filter === f ? ' active' : ''), onclick: () => { S.filter = f; updateList(); } },
        t('f_' + f) + ' ' + S.containers.filter(FILTERS[f]).length)));
    const shown = S.containers
      .filter((c) => FILTERS[S.filter](c) && (!S.q || c.name.toLowerCase().includes(S.q) || c.image.toLowerCase().includes(S.q)))
      .sort((a, b) => RANK[statusInfo(a).cls] - RANK[statusInfo(b).cls] || a.name.localeCompare(b.name));
    L.items.replaceChildren(...(shown.length ? shown.map(containerCard) : [h('div', { class: 'empty' }, t('no_containers'))]));
  }

  function buildDetail() {
    const D = { head: h('div'), banner: h('div'), actions: h('div', { class: 'actions' }), facts: h('div'),
      stats: h('div'), mute: h('div'), pre: h('pre', { class: 'logs' }, '…') };
    D.tail = h('select', { onchange: () => { S.tail = Number(D.tail.value); loadLogs(); } },
      [50, 100, 300].map((n) => h('option', { value: String(n), selected: n === S.tail }, t('lines', { n }))));
    const logsBar = h('div', { class: 'logs-head' }, D.tail,
      h('button', { class: 'btn secondary', onclick: loadLogs }, '⟳ ' + t('refresh')),
      h('button', { class: 'btn secondary', onclick: () => copyText(S.logs) }, '⧉ ' + t('copy')));
    D.root = h('div', {}, D.head, D.banner, D.actions, D.facts, D.stats, D.mute,
      h('div', { class: 'section' }, t('logs')), logsBar, D.pre);
    return D;
  }

  function updateDetail() {
    const D = V.detail, base = currentContainer();
    if (!D) return;
    if (!base) { if (S.loaded) { toast(t('err_gone')); go('list'); } return; }
    const c = Object.assign({}, base, S.extra && S.extra.id === base.id ? S.extra : {});
    const si = statusInfo(c), up = uptimeText(c);

    D.head.replaceChildren(h('div', { class: 'title' }, c.name),
      h('div', { class: 'row', style: 'margin:4px 4px 0' }, h('span', { class: 'dot ' + si.cls }),
        h('span', { class: 'badge ' + si.cls }, t(si.key)), h('span', { class: 'sub' }, up)));

    D.banner.replaceChildren(...maintenanceBanner());

    const runningLike = ['running', 'restarting', 'unhealthy', 'paused'].includes(c.status);
    const act = (action, cls) => h('button', { class: 'btn ' + cls, disabled: S.busy, onclick: () => doAction(c, action) }, t(action));
    D.actions.replaceChildren(...(canWrite() && !c.protected
      ? (runningLike ? [act('restart', ''), act('stop', 'danger')] : [act('start', '')]) : []));

    const notes = [];
    if (c.protected) notes.push(h('div', { class: 'card sub' }, t('protected')));
    else if (!canWrite()) notes.push(h('div', { class: 'card sub' }, t('read_only')));

    const rows = [[t('image'), c.image], [t('id'), c.short_id], [t('restarts'), c.restart_count],
      c.status === 'exited' ? [t('exit_code'), c.exit_code] : null,
      c.oom_killed ? [t('oom'), '⚠️'] : null,
      c.ports && c.ports.length ? [t('ports'), c.ports.join(', ')] : null,
      toDate(c.started_at) ? [t('started'), fmtDateTime(c.started_at)] : null,
      toDate(c.finished_at) && c.status !== 'running' ? [t('finished'), fmtDateTime(c.finished_at)] : null,
      c.health ? [t('health'), c.health] : null,
      c.health_output && c.health !== 'healthy' ? ['', c.health_output] : null].filter(Boolean);
    D.facts.replaceChildren(...notes, h('div', { class: 'card' },
      h('dl', { class: 'facts' }, rows.map((r) => [h('dt', {}, r[0]), h('dd', {}, String(r[1]))]))));

    const rec = S.mutes.find((m) => m.container_name === c.name);
    D.mute.replaceChildren(...(!canWrite() || S.maintenance ? [] : [rec
      ? h('div', { class: 'card' }, h('div', { class: 'sub' }, t('muted_until', { t: fmtDateTime(rec.until) })),
        h('div', { class: 'actions' }, h('button', { class: 'btn secondary', onclick: () => postUnmute(c.name) }, t('unmute'))))
      : h('div', { class: 'actions' }, h('button', { class: 'btn secondary', onclick: () => chooseMute(c.name, MUTE_CONTAINER()) }, t('mute')))]));
  }

  async function loadSystem() {
    try { S.system = await api('/api/system'); renderSystem(); } catch (e) { handleError(e); }
  }

  function renderSystem() {
    const R = V.system || (V.system = { root: h('div') });
    const s = S.system;
    if (!s) { R.root.replaceChildren(h('div', { class: 'boot' }, '…')); return; }
    const cls = (pct) => (pct >= 90 ? 'bad' : pct >= 75 ? 'warn' : '');
    const gauge = (label, pct, detail) => h('div', { class: 'card' },
      h('div', { class: 'row' }, h('div', { class: 'grow' }, label), h('b', { class: cls(pct) }, pct + '%')),
      h('div', { class: 'meter ' + cls(pct) }, h('span', { style: 'width:' + Math.min(100, pct) + '%' })),
      detail ? h('div', { class: 'sub' }, detail) : null);
    const bytes = (used, total) => fmtBytes(used) + ' / ' + fmtBytes(total);
    const facts = [
      [t('sys_uptime'), fmtDuration(s.uptime * 1000)],
      [t('sys_load'), s.load.join(' · ')],
      [t('sys_cores'), String(s.cores)],
      s.temp === null ? null : [t('sys_temp'), s.temp + ' °C'],
      [t('sys_containers'), t('sys_running', { r: s.containers_running, n: s.containers })],
      [t('sys_host'), s.host], [t('sys_os'), s.os], [t('sys_kernel'), s.kernel],
    ].filter(Boolean);
    R.root.replaceChildren(
      gauge(t('sys_cpu'), s.cpu_percent),
      gauge(t('sys_ram'), s.ram_percent, bytes(s.ram_used, s.ram_total)),
      ...(s.swap_total ? [gauge(t('sys_swap'), s.swap_percent, bytes(s.swap_used, s.swap_total))] : []),
      gauge(t('sys_disk'), s.disk_percent, bytes(s.disk_used, s.disk_total)),
      h('div', { class: 'card' }, h('dl', { class: 'facts' }, ...facts.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]))));
  }

  function ensureHistory() {
    if (V.history) return V.history;
    const H = { summary: h('div'), top: h('div', { class: 'chips' }), items: h('div'), more: h('div') };
    H.root = h('div', {}, H.summary, H.top, H.items, H.more);
    return (V.history = H);
  }

  function renderHistory() {
    const H = ensureHistory(), f = S.fail;
    if (!f) return;
    const sm = f.summary || {};
    const stat = (n, label) => h('div', { class: 'stat' }, h('b', {}, String(n === undefined ? '–' : n)), h('span', {}, label));
    H.summary.replaceChildren(h('div', { class: 'stats3' }, stat(sm.last_24h, t('f24')), stat(sm.last_7d, t('f7')), stat(sm.total, t('ftotal'))));

    const names = (sm.top || []).map((x) => x.container_name);
    if (S.failFilter && !names.includes(S.failFilter)) names.push(S.failFilter);
    const pick = (name) => () => { S.failFilter = name; loadHistory(false); };
    H.top.replaceChildren(...(names.length ? [h('button', { class: 'chip' + (S.failFilter ? '' : ' active'), onclick: pick('') }, t('all_containers')),
      ...names.map((n) => h('button', { class: 'chip' + (S.failFilter === n ? ' active' : ''), onclick: pick(n) }, n))] : []));

    const out = [];
    let day = '';
    for (const item of f.items) {
      const label = fmtDay(item.failed_at);
      if (label !== day) { day = label; out.push(h('div', { class: 'section' }, label)); }
      const known = S.containers.some((c) => c.name === item.container_name);
      out.push(h('div', { class: 'card' + (known ? ' tap' : ''), onclick: known ? () => go('detail', item.container_name) : null },
        h('div', { class: 'row' }, h('span', { class: 'dot bad' }),
          h('div', { class: 'grow' }, h('div', { class: 'name' }, item.container_name), h('div', { class: 'sub' }, fmtClock(item.failed_at))),
          h('span', { class: 'badge bad' }, item.reason))));
    }
    H.items.replaceChildren(...(out.length ? out : [h('div', { class: 'empty' }, t('no_failures'))]));
    H.more.replaceChildren(...(f.has_more ? [h('button', { class: 'btn secondary', style: 'width:100%', onclick: () => loadHistory(true) }, t('load_more'))] : []));
  }

  function renderSettings() {
    const R = V.settings || (V.settings = { root: h('div') });
    const me = S.me || { user: {}, role: '' };
    const muted = S.mutes.map((m) => h('div', { class: 'card' }, h('div', { class: 'row' },
      h('div', { class: 'grow' }, h('div', { class: 'name' }, m.container_name), h('div', { class: 'sub' }, t('muted_until', { t: fmtDateTime(m.until) }))),
      canWrite() ? h('button', { class: 'chip', onclick: () => postUnmute(m.container_name) }, t('unmute')) : null)));
    const actions = (S.actions || []).map((a) => h('div', { class: 'card' },
      h('div', { class: 'row' }, h('span', { class: 'dot ' + (a.ok ? 'ok' : 'bad') }),
        h('div', { class: 'grow' }, h('div', { class: 'name' }, a.action + ' · ' + a.container_name),
          h('div', { class: 'sub' }, a.user_name + ' · ' + fmtDateTime(a.at) + (a.detail ? ' · ' + a.detail : ''))))));

    const maint = h('div', { class: 'card' }, h('div', { class: 'name' }, t('maint')),
      h('div', { class: 'sub', style: 'white-space:normal' }, S.maintenance ? t('maint_on', { t: fmtDateTime(S.maintenance.until) }) : t('maint_desc')),
      canWrite() ? h('div', { class: 'actions' }, S.maintenance
        ? h('button', { class: 'btn secondary', onclick: () => postUnmute('*') }, t('maint_disable'))
        : h('button', { class: 'btn', onclick: () => chooseMute('*', MUTE_ALL()) }, t('maint_enable'))) : null);

    R.root.replaceChildren(
      h('div', { class: 'section' }, t('account')),
      h('div', { class: 'card' }, h('dl', { class: 'facts' },
        h('dt', {}, me.user.name || '—'), h('dd', {}, me.role === 'admin' ? t('role_admin') : t('role_viewer')),
        h('dt', {}, 'Telegram ID'), h('dd', {}, String(me.user.id || '')))),
      maint,
      h('div', { class: 'section' }, t('muted_list')),
      ...(muted.length ? muted : [h('div', { class: 'empty' }, t('no_mutes'))]),
      h('div', { class: 'section' }, t('action_log')),
      ...(actions.length ? actions : [h('div', { class: 'empty' }, t('no_actions'))]));
  }

  // ------------------------------------------------------------------------- //
  // Navigation / shell
  // ------------------------------------------------------------------------- //
  let backBound = false;
  function setBack(show) {
    if (!tg || !tg.BackButton) return;
    try {
      if (!backBound) { tg.BackButton.onClick(() => go('list')); backBound = true; }
      if (show) tg.BackButton.show(); else tg.BackButton.hide();
    } catch (e) { /* BackButton needs Telegram 6.1+ */ }
  }

  function go(view, name) {
    S.view = view;
    if (view === 'detail') S.cname = name;
    const tab = view === 'detail' ? 'list' : view;
    for (const k in shell.tabs) shell.tabs[k].classList.toggle('active', k === tab);
    setBack(view === 'detail');

    if (view === 'list') {
      shell.title.textContent = t('tab_containers');
      shell.main.replaceChildren(ensureList().root); updateList(); loadContainers();
    } else if (view === 'detail') {
      S.extra = null; S.logs = '';
      V.detail = buildDetail();
      shell.title.textContent = name;
      shell.main.replaceChildren(V.detail.root); updateDetail();
      loadContainers().then(() => {
        if (S.view !== 'detail') return;
        if (currentContainer()) { loadExtra(); loadLogs(); loadStats(); }
      });
    } else if (view === 'system') {
      shell.title.textContent = t('tab_system');
      shell.main.replaceChildren((V.system || (V.system = { root: h('div') })).root);
      renderSystem(); loadSystem();
    } else if (view === 'history') {
      shell.title.textContent = t('tab_history');
      shell.main.replaceChildren(ensureHistory().root); renderHistory(); loadHistory(false);
    } else {
      shell.title.textContent = t('tab_settings');
      shell.main.replaceChildren((V.settings || (V.settings = { root: h('div') })).root);
      renderSettings(); loadContainers(); loadSettings();
    }
  }

  function onRefresh() {
    if (S.view === 'history') return loadHistory(false);
    if (S.view === 'system') return loadSystem();
    loadContainers();
    if (S.view === 'detail') { loadLogs(); loadStats(); loadExtra(); }
    if (S.view === 'settings') loadSettings();
  }

  function buildShell() {
    const title = h('h1');
    const main = h('main');
    const tabs = {};
    const nav = h('nav', { class: 'tabs' }, [['list', '📦', 'tab_containers'], ['system', '🖥️', 'tab_system'], ['history', '🕘', 'tab_history'], ['settings', '⚙️', 'tab_settings']]
      .map(([view, icon, key]) => (tabs[view] = h('button', { onclick: () => go(view) }, h('span', { class: 'ico' }, icon), h('span', {}, t(key))))));
    root.replaceChildren(h('header', { class: 'top' }, title, h('button', { class: 'icon-btn', onclick: onRefresh, 'aria-label': t('refresh') }, '⟳')), main, nav);
    shell = { title, main, tabs };
  }

  async function boot() {
    if (tg) {
      try { tg.ready(); tg.expand(); if (tg.disableVerticalSwipes) tg.disableVerticalSwipes(); } catch (e) { /* older client */ }
    }
    if (!INIT) return fatal(t('err_open'));      // opened in a normal browser
    try { S.me = await api('/api/me'); } catch (e) { return handleError(e); }
    buildShell();

    // Alert buttons open the app as /?c=<container name>
    let deep = null;
    try { deep = new URLSearchParams(location.search).get('c'); } catch (e) { /* ignore */ }
    go(deep ? 'detail' : 'list', deep);

    // Live updates: poll while the app is visible only (saves battery and server load).
    const tick = () => {
      if (document.hidden || S.fatal) return;
      if (S.view === 'list' || S.view === 'detail' || S.view === 'settings') loadContainers();
      if (S.view === 'detail') loadStats();
      if (S.view === 'system') loadSystem();
    };
    setInterval(tick, 10000);
    document.addEventListener('visibilitychange', tick);
  }

  boot();
})();
