'use strict';

// Classic scripts share the starter's lexical scope. Read its grid and call its
// existing reset/apply function; do not copy the solver, renderer, or classifier.
(() => {
  const model = MapPortfolio;
  const store = model.createStore(() => window.localStorage);
  const byId = id => document.getElementById(id);
  const nameInput = byId('portfolio-name');
  const list = byId('portfolio-list');
  const fileInput = byId('portfolio-import');
  const fieldset = byId('portfolio-controls');
  const status = byId('portfolio-status');
  const dialog = byId('portfolio-confirm');
  const workspace = document.querySelector('.workspace');
  let pending = false;
  let boundName = null;

  function displayName(name) {
    nameInput.value = name;
    // Form controls normalize CR/CRLF to LF. Keep the exact valid imported or
    // loaded name until the user edits it, so file roundtrips cannot rename it.
    boundName = {raw: name, displayed: nameInput.value};
  }

  nameInput.addEventListener('input', () => { boundName = null; });

  function report(message, error = false) {
    status.textContent = message;
    status.classList.toggle('error', error);
  }

  function selectionChanged() {
    byId('portfolio-load').disabled = !list.value;
    byId('portfolio-delete').disabled = !list.value;
  }

  function renderRecords(records, selected = list.value) {
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = records.length ? '请选择地图' : '尚无已保存地图';
    list.replaceChildren(empty);
    for (const record of records) {
      const option = document.createElement('option');
      option.value = record.name;
      option.textContent = record.name;
      list.append(option);
    }
    list.value = records.some(record => record.name === selected) ? selected : '';
    selectionChanged();
  }

  function ask(message) {
    byId('portfolio-confirm-text').textContent = message;
    dialog.returnValue = '';
    return new Promise(resolve => {
      const onClose = () => resolve(dialog.returnValue === 'confirm');
      dialog.addEventListener('close', onClose, {once: true});
      dialog.showModal();
      byId('portfolio-confirm-no').focus();
    });
  }

  // Lock both map changes and portfolio controls across asynchronous file reads
  // and confirmation. A response for an old grid must not be applied to a new one.
  async function perform(operation, trigger) {
    if (pending || busy) {
      report('正在处理其他操作，请稍后再试。', true);
      return;
    }
    if (!grid.length) {
      report('地图尚未载入，请等待本机服务准备好后再试。', true);
      return;
    }
    pending = true;
    busy = true;
    fieldset.disabled = true;
    const wasInert = workspace.inert;
    workspace.inert = true;
    try {
      await operation();
    } catch (error) {
      report(error.message || '操作失败，当前地图与已有存档保持不变。', true);
    } finally {
      pending = false;
      busy = false;
      fieldset.disabled = false;
      workspace.inert = wasInert;
      selectionChanged();
      if (trigger && !trigger.disabled) trigger.focus();
      else if (trigger) list.focus();
    }
  }

  function currentDocument() {
    const name = boundName && nameInput.value === boundName.displayed ? boundName.raw : nameInput.value;
    return model.validateDocument({version: 1, name, grid: grid.slice()});
  }

  async function saveDocument(document) {
    try {
      return store.save(document);
    } catch (error) {
      if (error.code !== 'duplicate') throw error;
      const confirmed = await ask(`已有同名地图「${document.name}」。确认将只覆盖这张地图；取消后可修改名称另存。`);
      if (!confirmed) {
        report('已取消覆盖；已有存档保持不变，可修改名称后另存。');
        return null;
      }
      return store.save(document, {overwrite: true});
    }
  }

  function applyDocument(document) {
    // setMap clears route/comparisons and stops replay, but keeps glyph samples.
    // A pending recognized direction also becomes stale when the map changes.
    invalidatePrediction();
    byId('prediction').textContent = '地图已切换；请重新识别并确认后执行。';
    setMap(document.grid, document.name, '这是你的地图作品。请在同一张地图上比较策略。');
    window.document.querySelectorAll('#presets button').forEach(button => button.classList.remove('active'));
  }

  byId('portfolio-form').addEventListener('submit', event => {
    event.preventDefault();
    const trigger = document.activeElement;
    void perform(async () => {
      const document = currentDocument();
      const records = await saveDocument(document);
      if (!records) return;
      displayName(document.name);
      renderRecords(records, document.name);
      report('地图已保存到当前浏览器。刷新后从列表选择并加载。');
    }, trigger);
  });

  list.addEventListener('change', selectionChanged);
  byId('portfolio-load').addEventListener('click', event => {
    const selected = list.value;
    void perform(() => {
      const result = store.read();
      const document = result.records.find(record => record.name === selected);
      if (!document) throw Error(result.warnings.join(' ') || '所选地图已不存在，请刷新存档列表。');
      applyDocument(document);
      displayName(document.name);
      renderRecords(result.records, document.name);
      report(`已加载地图「${document.name}」。${result.warnings.join(' ')}`, !!result.warnings.length);
    }, event.currentTarget);
  });

  byId('portfolio-delete').addEventListener('click', event => {
    const selected = list.value;
    void perform(async () => {
      if (!selected) throw Error('请先选择要删除的地图。');
      if (!await ask(`删除存档「${selected}」？此操作只删除所选本地存档，当前地图仍保留。`)) {
        report('已取消删除；已有存档保持不变。');
        return;
      }
      const records = store.remove(selected);
      renderRecords(records, '');
      report('所选地图存档已删除；当前地图保持不变。');
    }, event.currentTarget);
  });

  byId('portfolio-export').addEventListener('click', event => {
    void perform(() => {
      const document = currentDocument();
      const blob = new Blob([JSON.stringify(document, null, 2)], {type: 'application/json;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement('a');
      anchor.href = url;
      anchor.download = 'robot-map.json';
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      report('已导出当前地图 JSON。请自行保存文件，再手动交给同学导入。');
    }, event.currentTarget);
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (!file) return;
    void perform(async () => {
      const document = await model.readFile(file);
      const records = await saveDocument(document);
      if (!records) return;
      // Persistence is complete before committing any new application state.
      applyDocument(document);
      displayName(document.name);
      renderRecords(records, document.name);
      report('地图 JSON 已导入、保存并加载到当前浏览器。');
    }, fileInput).finally(() => { fileInput.value = ''; });
  });

  byId('portfolio-confirm-yes').addEventListener('click', () => dialog.close('confirm'));
  byId('portfolio-confirm-no').addEventListener('click', () => dialog.close('cancel'));
  dialog.addEventListener('cancel', event => { event.preventDefault(); dialog.close('cancel'); });

  const initial = store.read();
  renderRecords(initial.records);
  report(initial.warnings.length ? initial.warnings.join(' ') : '为当前地图命名后保存；刷新后从列表加载。', !!initial.warnings.length);
})();
