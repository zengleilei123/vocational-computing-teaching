/* Teacher reference only: the V1/V2 map document and storage contract.
 * No solver result, replay state, or classifier training sample belongs here.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.MapPortfolio = api;
  }
})(globalThis, function () {
  'use strict';

  const STORAGE_KEY = 'robot-map-portfolio:v1';
  const MAX_FILE_BYTES = 16 * 1024;

  class PortfolioError extends Error {
    constructor(code, message) {
      super(message);
      this.name = 'PortfolioError';
      this.code = code;
    }
  }

  function invalidDocument(message) {
    return new PortfolioError('invalid-document', message);
  }

  function normalizeName(input) {
    if (typeof input !== 'string') {
      throw invalidDocument('地图名称必须是字符串。');
    }
    const name = input.trim();
    // JS string.length counts UTF-16 code units. Array.from counts code points,
    // so one non-BMP character (for example 🧭) counts as one, not two.
    const length = Array.from(name).length;
    if (length < 1 || length > 40) {
      throw invalidDocument('地图名称去除首尾空白后需要 1–40 个 Unicode 码点。');
    }
    return name;
  }

  function validateDocument(input) {
    if (input === null || typeof input !== 'object' || Array.isArray(input)) {
      throw invalidDocument('地图文件顶层必须是包含 version、name、grid 的对象。');
    }
    const keys = Reflect.ownKeys(input);
    if (keys.length !== 3 || !['version', 'name', 'grid'].every((key) => keys.includes(key))) {
      throw invalidDocument('地图文件只能包含 version、name、grid 三个字段，且不能缺少字段。');
    }
    if (!Number.isInteger(input.version) || input.version !== 1) {
      throw invalidDocument('地图文件的 version 必须是整数 1。');
    }
    const name = normalizeName(input.name);
    const grid = input.grid;
    if (!Array.isArray(grid) || grid.length < 3 || grid.length > 20) {
      throw invalidDocument('地图需要 3–20 行。');
    }
    for (const row of grid) {
      if (typeof row !== 'string') {
        throw invalidDocument('地图的每一行必须是字符串。');
      }
    }
    const width = grid[0].length;
    if (width < 3 || width > 20 || grid.some((row) => row.length !== width)) {
      throw invalidDocument('地图需要等宽的 3–20 列。');
    }
    let starts = 0;
    let goals = 0;
    for (const row of grid) {
      for (const cell of row) {
        if (!'#.SG23456789'.includes(cell)) {
          throw invalidDocument('地图只允许 # . S G 和数字 2–9。');
        }
        if (cell === 'S') starts += 1;
        if (cell === 'G') goals += 1;
      }
    }
    if (starts !== 1 || goals !== 1) {
      throw invalidDocument('地图必须恰好有一个 S 和一个 G。');
    }
    // Reachability is a solver result, not a document validity requirement.
    return { version: 1, name, grid: grid.slice() };
  }

  async function readFile(file) {
    if (!file || !Number.isSafeInteger(file.size) || file.size < 0) {
      throw new PortfolioError('file-read', '无法读取所选文件的大小，请重新选择 JSON 文件。');
    }
    // This check must precede arrayBuffer(), decoding, and JSON parsing.
    if (file.size > MAX_FILE_BYTES) {
      throw new PortfolioError('file-too-large', '地图文件超过 16 KiB（16384 字节），未读取文件。');
    }
    let bytes;
    try {
      bytes = new Uint8Array(await file.arrayBuffer());
    } catch (_error) {
      throw new PortfolioError('file-read', '无法读取所选文件，请重新选择后重试。');
    }
    if (bytes.byteLength > MAX_FILE_BYTES) {
      throw new PortfolioError('file-too-large', '地图文件实际内容超过 16 KiB（16384 字节）。');
    }
    let text;
    try {
      text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    } catch (_error) {
      throw new PortfolioError('invalid-utf8', '地图文件不是有效的 UTF-8 文本，请使用 UTF-8 JSON 文件。');
    }
    let input;
    try {
      input = JSON.parse(text);
    } catch (_error) {
      throw new PortfolioError('invalid-json', '地图文件的 JSON 格式错误，请检查后重新导入。');
    }
    return validateDocument(input);
  }

  function copyRecords(records) {
    return records.map(({ version, name, grid }) => ({ version, name, grid: grid.slice() }));
  }

  function persist(storage, records) {
    try {
      storage.setItem(STORAGE_KEY, JSON.stringify(records));
    } catch (_error) {
      throw new PortfolioError('storage-write', '本地存储写入失败，存档未更新。请检查存储权限或剩余空间，并导出地图备份。');
    }
    // Nothing is reported as saved until setItem has returned successfully.
    return copyRecords(records);
  }

  function createStore(storageProvider = () => globalThis.localStorage) {
    function snapshot() {
      let storage;
      let raw;
      try {
        storage = storageProvider();
        raw = storage.getItem(STORAGE_KEY);
      } catch (_error) {
        const error = new PortfolioError('storage-unavailable',
          '无法访问浏览器本地存储。当前地图仍可编辑和导出，请检查浏览器存储权限。');
        return { records: [], warnings: [error.message], available: false, error };
      }
      if (raw === null) {
        return { records: [], warnings: [], available: true, storage };
      }
      let entries;
      try {
        entries = JSON.parse(raw);
        if (!Array.isArray(entries)) throw new Error('Expected an array');
      } catch (_error) {
        const error = new PortfolioError('storage-corrupt',
          '存档容器损坏，已保留原数据；请先备份并修复或移除该存储项。当前地图仍可编辑和导出。');
        return { records: [], warnings: [error.message], available: false, error };
      }
      const records = [];
      const warnings = [];
      const names = new Set();
      entries.forEach((entry, index) => {
        let record;
        try {
          record = validateDocument(entry);
        } catch (error) {
          warnings.push(`已忽略第 ${index + 1} 条无效存档：${error.message}`);
          return;
        }
        if (names.has(record.name)) {
          warnings.push(`已忽略第 ${index + 1} 条重复名称存档“${record.name}”，保留前一条有效记录。`);
          return;
        }
        names.add(record.name);
        records.push(record);
      });
      // Reading never repairs or rewrites bytes. An explicit successful later
      // mutation serializes only the recovered valid records plus its change.
      return { records, warnings, available: true, storage };
    }

    return {
      read() {
        const { records, warnings, available } = snapshot();
        return { records, warnings, available };
      },

      save(input, { overwrite = false } = {}) {
        const record = validateDocument(input);
        // Reload for each change so sequential tabs/stores see recent changes.
        // localStorage has no cross-tab transaction: simultaneous edits can race.
        const current = snapshot();
        if (!current.available) throw current.error;
        const index = current.records.findIndex((saved) => saved.name === record.name);
        if (index >= 0 && overwrite !== true) {
          throw new PortfolioError('duplicate',
            `已存在名为“${record.name}”的地图，请改名或明确选择覆盖。`);
        }
        if (index >= 0) {
          current.records[index] = record;
        } else {
          current.records.push(record);
        }
        return persist(current.storage, current.records);
      },

      remove(inputName) {
        const name = normalizeName(inputName);
        const current = snapshot();
        if (!current.available) throw current.error;
        const index = current.records.findIndex((record) => record.name === name);
        if (index < 0) {
          throw new PortfolioError('not-found', '该地图存档不存在或已删除，请刷新存档列表。');
        }
        current.records.splice(index, 1);
        return persist(current.storage, current.records);
      },
    };
  }

  return { STORAGE_KEY, MAX_FILE_BYTES, PortfolioError, validateDocument, readFile, createStore };
});
