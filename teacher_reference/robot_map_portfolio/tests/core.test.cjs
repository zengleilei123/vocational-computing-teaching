'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {
  STORAGE_KEY,
  MAX_FILE_BYTES,
  PortfolioError,
  validateDocument,
  readFile,
  createStore,
} = require('../static/portfolio-core.js');

const SIMPLE_GRID = ['S..', '.#.', '..G'];
const OTHER_GRID = ['S2.', '###', '..G'];

function document(name = '校园地图', grid = SIMPLE_GRID) {
  return { version: 1, name, grid: grid.slice() };
}

// This substitute is deliberately confined to tests. Production receives the
// browser's Storage object through a provider, including its real exceptions.
function memoryStorage(raw = null) {
  return {
    raw,
    reads: 0,
    writes: 0,
    attempts: 0,
    readError: null,
    writeError: null,
    getItem(key) {
      assert.equal(key, STORAGE_KEY);
      this.reads += 1;
      if (this.readError) throw this.readError;
      return this.raw;
    },
    setItem(key, value) {
      assert.equal(key, STORAGE_KEY);
      this.attempts += 1;
      if (this.writeError) throw this.writeError;
      this.raw = String(value);
      this.writes += 1;
    },
  };
}

function byteFile(bytes, declaredSize = bytes.byteLength) {
  return {
    size: declaredSize,
    reads: 0,
    async arrayBuffer() {
      this.reads += 1;
      return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    },
  };
}

function jsonFile(value) {
  return byteFile(new TextEncoder().encode(JSON.stringify(value)));
}

function errorWith(code) {
  return (error) => {
    assert.ok(error instanceof PortfolioError);
    assert.equal(error.code, code);
    assert.match(error.message, /[\u3400-\u9fff]/, '错误应为可读的中文提示');
    return true;
  };
}

test('公开接口可在 Node 和无模块浏览器环境使用', () => {
  assert.equal(STORAGE_KEY, 'robot-map-portfolio:v1');
  assert.equal(MAX_FILE_BYTES, 16 * 1024);
  const source = fs.readFileSync(path.join(__dirname, '../static/portfolio-core.js'), 'utf8');
  const browser = vm.createContext({ TextDecoder });
  vm.runInContext(source, browser);
  assert.equal(browser.MapPortfolio.STORAGE_KEY, STORAGE_KEY);
  assert.equal(typeof browser.MapPortfolio.createStore, 'function');
  assert.equal(typeof browser.MapPortfolio.readFile, 'function');
});

test('A01 合法文档规范化名称并返回独立对象和网格', () => {
  const input = document('  校园地图\n');
  const normalized = validateDocument(input);
  assert.deepEqual(normalized, document());
  assert.notEqual(normalized, input);
  assert.notEqual(normalized.grid, input.grid);
  normalized.grid[0] = 'G..';
  assert.equal(input.grid[0], 'S..');
  assert.equal(input.name, '  校园地图\n');
});

test('A02 名称按 Unicode 码点计算：40 个非 BMP 字符可用，41 个被拒绝', () => {
  const forty = '🧭'.repeat(40);
  assert.equal(forty.length, 80);
  assert.equal(validateDocument(document(` \t${forty}\n `)).name, forty);
  for (const name of ['🧭'.repeat(41), '汉'.repeat(41), '', ' \n\t ', null, 9, true, []]) {
    assert.throws(() => validateDocument(document(name)), errorWith('invalid-document'));
  }
  assert.equal(validateDocument(document('汉'.repeat(40))).name, '汉'.repeat(40));
});

test('A05 顶层只能是具备三个指定字段的对象，版本只能是整数 1', () => {
  const invalid = [null, [], '', 1, true, {}, { version: 1, name: '缺地图' }];
  for (const version of [true, false, '1', 0, 2, 1.1, null, undefined, NaN, Infinity]) {
    invalid.push({ ...document(), version });
  }
  invalid.push({ ...document(), samples: [] });
  invalid.push({ ...document(), runtime: { actions: ['right'] } });
  invalid.push({ ...document(), [Symbol('extra')]: true });
  for (const input of invalid) {
    assert.throws(() => validateDocument(input), errorWith('invalid-document'));
  }
});

test('A06 地图约束与 engine.parse_grid 一致，同时允许无路可达的地图', () => {
  const twenty = ['S' + '.'.repeat(19), ...Array(18).fill('.'.repeat(20)), '.'.repeat(19) + 'G'];
  assert.deepEqual(validateDocument(document('最大地图', twenty)).grid, twenty);
  assert.deepEqual(validateDocument(document('无路可达', OTHER_GRID)).grid, OTHER_GRID);
  assert.deepEqual(validateDocument(document('全部数字', ['S23456789', '.........', '........G'])).grid,
    ['S23456789', '.........', '........G']);
  const invalidGrids = [
    null, 'S..\n.#.\n..G', [], ['S..', '..G'],
    ['S..', ...Array(19).fill('...'), '..G'],
    ['S.', '..', '.G'],
    ['S' + '.'.repeat(20), '.'.repeat(21), '.'.repeat(20) + 'G'],
    ['S..', '....', '..G'], ['S..', 3, '..G'],
    ['...', '.#.', '..G'], ['S..', '.#.', '...'],
    ['SS.', '.#.', '..G'], ['S..', '.G.', '..G'],
    ['S0.', '...', '..G'], ['S1.', '...', '..G'],
    ['Sg.', '...', '..G'], ['S .', '...', '..G'],
    ['S🧭', '...', '..G'], ['S..\n', '....', '...G'],
    ['S..', , '..G'],
  ];
  for (const grid of invalidGrids) {
    assert.throws(() => validateDocument({ version: 1, name: '非法地图', grid }),
      errorWith('invalid-document'));
  }
});

test('A07 恰好 16384 字节的 UTF-8 JSON 可导入', async () => {
  const json = JSON.stringify(document('字节边界'));
  const padding = MAX_FILE_BYTES - new TextEncoder().encode(json).byteLength;
  const file = byteFile(new TextEncoder().encode(json + ' '.repeat(padding)));
  assert.equal(file.size, 16384);
  assert.deepEqual(await readFile(file), document('字节边界'));
  assert.equal(file.reads, 1);
});

test('A07 16385 字节文件在读取和解析前被拒绝', async () => {
  const file = {
    size: 16385,
    reads: 0,
    async arrayBuffer() {
      this.reads += 1;
      throw new Error('超限文件不应该执行读取');
    },
  };
  await assert.rejects(readFile(file), errorWith('file-too-large'));
  assert.equal(file.reads, 0);
});

test('A07 字节数不能按 UTF-16 字符串长度计算，实际读取结果也不能绕过上限', async () => {
  const file = byteFile(new TextEncoder().encode('汉'.repeat(6000)));
  assert.equal(file.size, 18000);
  await assert.rejects(readFile(file), errorWith('file-too-large'));
  assert.equal(file.reads, 0);
  const falseSize = byteFile(new Uint8Array(16385), 0);
  await assert.rejects(readFile(falseSize), errorWith('file-too-large'));
});

test('A05 导入必须严格解码 UTF-8，拒绝损坏字节而非替换字符', async () => {
  const prefix = new TextEncoder().encode('{"version":1,"name":"');
  const suffix = new TextEncoder().encode('","grid":["S..",".#.","..G"]}');
  const malformed = new Uint8Array([...prefix, 0xc3, 0x28, ...suffix]);
  await assert.rejects(readFile(byteFile(malformed)), errorWith('invalid-utf8'));
  await assert.rejects(readFile(byteFile(new Uint8Array([0xff, 0xfe, 0x7b, 0x00]))),
    errorWith('invalid-utf8'));
});

test('A05 JSON 语法错误和不符合契约的文件都被拒绝', async () => {
  await assert.rejects(readFile(byteFile(new TextEncoder().encode('{bad json'))),
    errorWith('invalid-json'));
  for (const value of [[], null, { ...document(), version: '1' }, { ...document(), samples: [] },
    document('重复起点', ['SS.', '...', '..G'])]) {
    await assert.rejects(readFile(jsonFile(value)), errorWith('invalid-document'));
  }
});

test('读取文件失败会返回可读错误；导入仅校验，不修改调用者数据', async () => {
  await assert.rejects(readFile({ size: 1, async arrayBuffer() { throw new Error('读盘失败'); } }),
    errorWith('file-read'));
  const input = document('  导入地图  ');
  const file = jsonFile(input);
  assert.deepEqual(await readFile(file), document('导入地图'));
  assert.equal(input.name, '  导入地图  ');
});

test('A01 空存储读取不写入；保存后新建 store 可恢复相同文档', () => {
  const storage = memoryStorage();
  const store = createStore(() => storage);
  assert.deepEqual(store.read(), { records: [], warnings: [], available: true });
  assert.equal(storage.writes, 0);
  const result = store.save(document());
  assert.deepEqual(result, [document()]);
  assert.deepEqual(JSON.parse(storage.raw), [document()]);
  assert.deepEqual(createStore(() => storage).read(), {
    records: [document()], warnings: [], available: true,
  });
  assert.equal(storage.writes, 1);
});

test('A01 保存、加载只返回文档字段，修改返回值不会修改持久化记录', () => {
  const storage = memoryStorage();
  const store = createStore(() => storage);
  const input = document();
  const saved = store.save(input);
  saved[0].name = '仅修改返回值';
  saved[0].grid[0] = 'G..';
  input.grid[1] = '...';
  const loaded = store.read();
  loaded.records[0].grid[0] = 'G..';
  loaded.records.push(document('内存附加'));
  assert.deepEqual(store.read().records, [document()]);
  assert.deepEqual(Object.keys(JSON.parse(storage.raw)[0]).sort(), ['grid', 'name', 'version']);
});

test('A03 同名存档先拒绝，显式覆盖只修改匹配地图并保留其他记录', () => {
  const storage = memoryStorage(JSON.stringify([document('A'), document('B')]));
  const store = createStore(() => storage);
  const rawBefore = storage.raw;
  assert.throws(() => store.save(document(' A ', OTHER_GRID)), errorWith('duplicate'));
  assert.equal(storage.raw, rawBefore);
  assert.equal(storage.writes, 0);
  assert.throws(() => store.save(document('A', OTHER_GRID), { overwrite: 'true' }),
    errorWith('duplicate'));
  assert.deepEqual(store.save(document(' A ', OTHER_GRID), { overwrite: true }),
    [document('A', OTHER_GRID), document('B')]);
  assert.deepEqual(JSON.parse(storage.raw), [document('A', OTHER_GRID), document('B')]);
  assert.equal(storage.writes, 1);
});

test('A03 名称比较去首尾空白、区分大小写，并安全支持特殊属性名', () => {
  const storage = memoryStorage();
  const store = createStore(() => storage);
  for (const name of ['A', 'a', '__proto__', 'constructor', '<b>地图</b>']) {
    store.save(document(name));
  }
  assert.deepEqual(store.read().records.map((record) => record.name),
    ['A', 'a', '__proto__', 'constructor', '<b>地图</b>']);
  assert.throws(() => store.save(document(' A ')), errorWith('duplicate'));
});

test('A02 非法保存不能影响已有记录，也不访问或写入存储', () => {
  const storage = memoryStorage(JSON.stringify([document('保留')]));
  const store = createStore(() => storage);
  const before = storage.raw;
  for (const invalid of [document(' '), document('🧭'.repeat(41)),
    { ...document(), version: true }, { ...document(), samples: [] }]) {
    assert.throws(() => store.save(invalid), errorWith('invalid-document'));
    assert.equal(storage.raw, before);
  }
  assert.equal(storage.reads, 0);
  assert.equal(storage.writes, 0);
});

test('A04 删除匹配名称后保留其他记录；不存在的名称不会写入或伪报删除', () => {
  const storage = memoryStorage(JSON.stringify([document('A'), document('B')]));
  const store = createStore(() => storage);
  assert.deepEqual(store.remove(' A '), [document('B')]);
  assert.deepEqual(JSON.parse(storage.raw), [document('B')]);
  const before = storage.raw;
  assert.throws(() => store.remove('A'), errorWith('not-found'));
  assert.equal(storage.raw, before);
  assert.equal(storage.writes, 1);
});

test('A09 写入失败时保存、覆盖和删除均不伪报成功或改变已有存档', () => {
  const existing = [document('A'), document('B')];
  const storage = memoryStorage(JSON.stringify(existing));
  const store = createStore(() => storage);
  const rawBefore = storage.raw;
  storage.writeError = new Error('QuotaExceededError');
  const operations = [
    () => store.save(document('C')),
    () => store.save(document('A', OTHER_GRID), { overwrite: true }),
    () => store.remove('A'),
  ];
  for (const operation of operations) {
    assert.throws(operation, errorWith('storage-write'), '写入抛错时不能返回成功记录');
    assert.equal(storage.raw, rawBefore, '存储中的原始字节应保持不变');
    assert.deepEqual(store.read().records, existing, '失败不能产生虚假内存状态');
  }
  assert.equal(storage.attempts, 3);
  assert.equal(storage.writes, 0);
  storage.writeError = null;
  assert.deepEqual(store.save(document('C')), [...existing, document('C')]);
});

test('A09 无法访问存储时读取降级、变更明确失败，不伪装成空存储', () => {
  const inaccessible = memoryStorage(JSON.stringify([document('A')]));
  inaccessible.readError = new Error('SecurityError');
  const providers = [
    () => { throw new Error('SecurityError'); },
    () => null,
    () => inaccessible,
  ];
  for (const provider of providers) {
    const store = createStore(provider);
    const read = store.read();
    assert.equal(read.available, false);
    assert.deepEqual(read.records, []);
    assert.ok(read.warnings.length > 0);
    assert.throws(() => store.save(document()), errorWith('storage-unavailable'));
    assert.throws(() => store.remove('A'), errorWith('storage-unavailable'));
  }
  assert.equal(inaccessible.writes, 0);
  assert.deepEqual(JSON.parse(inaccessible.raw), [document('A')]);
});

test('A09 默认 provider 延迟读取 localStorage，访问被禁用时可读降级', () => {
  const source = fs.readFileSync(path.join(__dirname, '../static/portfolio-core.js'), 'utf8');
  const browser = vm.createContext({ TextDecoder });
  vm.runInContext(source, browser);
  Object.defineProperty(browser, 'localStorage', {
    get() { throw new Error('SecurityError'); },
  });
  const store = browser.MapPortfolio.createStore();
  assert.equal(store.read().available, false);
  assert.throws(() => store.save(document()), /本地存储/);
});

test('A09 整个容器 JSON 损坏或不是数组时保留原字节并阻止覆盖', () => {
  for (const raw of ['{bad json', '', '{}', 'null', '"字符串"', '1']) {
    const storage = memoryStorage(raw);
    const store = createStore(() => storage);
    const read = store.read();
    assert.equal(read.available, false);
    assert.deepEqual(read.records, []);
    assert.ok(read.warnings.some((warning) => /损坏/.test(warning) && /保留/.test(warning)));
    assert.equal(storage.raw, raw);
    assert.equal(storage.writes, 0);
    assert.throws(() => store.save(document()), errorWith('storage-corrupt'));
    assert.throws(() => store.remove('A'), errorWith('storage-corrupt'));
    assert.equal(storage.raw, raw);
    assert.equal(storage.writes, 0);
  }
});

test('A09 混合坏记录和重复名称时恢复有效记录、显示警告且读取不改写', () => {
  const entries = [document('A'), null, { ...document('旧版本'), version: 2 },
    document(' A ', OTHER_GRID), document('B'), { ...document('多余字段'), samples: [] }];
  const raw = JSON.stringify(entries);
  const storage = memoryStorage(raw);
  const store = createStore(() => storage);
  const read = store.read();
  assert.equal(read.available, true);
  assert.deepEqual(read.records, [document('A'), document('B')]);
  assert.equal(read.warnings.length, 4);
  assert.ok(read.warnings.some((warning) => /重复/.test(warning)));
  assert.equal(storage.raw, raw);
  assert.equal(storage.writes, 0);
  assert.deepEqual(store.save(document('C')), [document('A'), document('B'), document('C')]);
  assert.deepEqual(JSON.parse(storage.raw), [document('A'), document('B'), document('C')]);
});

test('变更前读取最新记录，避免顺序使用的不同 store 覆盖彼此新增记录', () => {
  const storage = memoryStorage();
  const first = createStore(() => storage);
  const second = createStore(() => storage);
  first.read();
  second.read();
  first.save(document('A'));
  second.save(document('B'));
  assert.deepEqual(first.read().records, [document('A'), document('B')]);
  first.remove('A');
  assert.deepEqual(second.save(document('C')), [document('B'), document('C')]);
});
