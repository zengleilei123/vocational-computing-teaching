'use strict';
const $ = id => document.getElementById(id);
const names = {up:'上', right:'右', down:'下', left:'左'};
const strategyNames = {bfs:'BFS', dijkstra:'Dijkstra', student:'我的策略'};
const deltas = {up:[-1,0], right:[0,1], down:[1,0], left:[0,-1]};
let maps = [], demoTrain = [], grid = [], path = [], actions = [], costs = [0];
let comparisons = [], train = [], test = [], pixels = Array(25).fill(0), prediction = null;
let brush = 'play', timer = null, route = null, busy = false, draw = false, paint = 1;
let recognitionVersion = 0, dataVersion = 0;
const clone = value => JSON.parse(JSON.stringify(value));
function notice(text, error=false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
async function api(endpoint, data) {
  const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '请求失败');
  return result;
}
function stop() { if (timer) clearInterval(timer); timer = null; $('play').textContent='播放路线'; }
function startPosition() { for(let r=0;r<grid.length;r++) for(let c=0;c<grid[r].length;c++) if(grid[r][c]==='S') return [r,c]; }
function reset() {
  stop(); actions=[]; path=[startPosition()]; costs=[0]; route=null;
  $('frame').max=0; $('frame').value=0; $('frame').disabled=true; $('play').disabled=true;
  $('frame-label').textContent='0 / 0'; $('mode-label').textContent='手动探索'; renderMap();
}
function renderMap() {
  const end=path[path.length-1];
  $('grid').style.gridTemplateColumns=`repeat(${grid[0].length},minmax(0,1fr))`;
  $('grid').replaceChildren();
  grid.forEach((row,r)=>[...row].forEach((value,c)=>{
    const cell=document.createElement('button'); cell.type='button'; cell.className='cell';
    cell.classList.toggle('wall',value==='#'); cell.classList.toggle('rough',/[2-9]/.test(value));
    cell.classList.toggle('start',value==='S'); cell.classList.toggle('goal',value==='G');
    cell.classList.toggle('trail',path.some(p=>p[0]===r && p[1]===c));
    const robot=end && end[0]===r && end[1]===c; cell.classList.toggle('robot',robot);
    cell.textContent=robot?'R':(value==='.' || value==='#'?'':value);
    cell.setAttribute('aria-label',`第${r+1}行第${c+1}列，${robot?'机器人，':''}${value==='#'?'墙':value==='.'?'普通地面':value}`);
    cell.addEventListener('click',()=>editCell(r,c)); $('grid').append(cell);
  }));
  $('steps').textContent=Math.max(0,path.length-1); $('energy').textContent=costs[costs.length-1]||0;
  $('state').textContent=end && grid[end[0]][end[1]]==='G'?'已到达':path.length>1?'探索中':'待出发';
}
function setMap(rows, title='我的自创关卡', question='你希望哪个策略获胜？用同一关卡验证。') {
  grid=rows.slice(); comparisons=[]; $('map-title').textContent=title; $('question').textContent=question;
  $('map-text').value=grid.join('\n'); reset(); renderComparisons();
}
function editCell(r,c) {
  if(busy || brush==='play') return;
  if((grid[r][c]==='S'||grid[r][c]==='G') && brush!=='S' && brush!=='G') return notice('先把起点/终点移动到别处，再修改这里。',true);
  if((grid[r][c]==='S' && brush==='G')||(grid[r][c]==='G' && brush==='S')) return notice('起点和终点不能放在同一格。',true);
  const rows=grid.map(row=>[...row]);
  if(brush==='S'||brush==='G') rows.forEach(row=>row.forEach((v,i)=>{if(v===brush) row[i]='.';}));
  rows[r][c]=brush; setMap(rows.map(row=>row.join('')));
  notice('地图已修改。对比记录已清空，请重新检验你的预测。');
}
function renderComparisons() {
  $('comparisons').replaceChildren();
  if(!comparisons.length){const tr=document.createElement('tr'); const td=document.createElement('td');td.colSpan=4;td.textContent='运行算法后显示；修改地图会清空对比。';tr.append(td);$('comparisons').append(tr);return;}
  for(const item of comparisons){const tr=document.createElement('tr');
    for(const text of [item.name,item.success?'到达':'未到达',item.steps??'—',item.energy??'—']){const td=document.createElement('td');td.textContent=text;tr.append(td);} $('comparisons').append(tr);
  }
}
function saveComparison(name,result){comparisons=comparisons.filter(row=>row.name!==name);comparisons.push({name,...clone(result)});renderComparisons();}
async function move(direction) {
  if(busy || brush!=='play') return;
  if(route) reset();
  busy=true;
  try {
    const result=await api('/api/replay',{grid,actions:[...actions,direction]});
    if(['blocked','after_goal'].includes(result.reason)) return notice(result.reason==='blocked'?'前面是墙或边界。试着修改策略，而不是修改评分。':'已经到达，先回到起点再挑战。',true);
    actions.push(direction);path=result.path;costs.push(result.energy);renderMap();
    if(result.success){saveComparison('手动探索',result);notice(`到达！走了 ${result.steps} 步，消耗 ${result.energy}。试试有没有更省电的路线。`);}
    else notice('机器人移动了一步。普通地面耗能 1，高耗能格按数字计。');
  } catch(error){notice(error.message,true);} finally {busy=false;}
}
async function run(algorithm) {
  if(busy) return; busy=true; stop();
  try{
    const result=await api('/api/solve',{grid,algorithm}); saveComparison(strategyNames[algorithm],result);
    route=result; $('mode-label').textContent=strategyNames[algorithm]+' 路线';
    $('frame').max=Math.max(0,result.path.length-1);$('frame').value=0;$('frame').disabled=result.path.length<2;$('play').disabled=result.path.length<2;
    if(result.path.length) showFrame(0); else {path=[startPosition()];costs=[0];renderMap();$('frame-label').textContent='0 / 0';}
    notice(result.success?`${strategyNames[algorithm]}：${result.steps} 步，能耗 ${result.energy}。拖动滑块或播放，观察走法。`:`${strategyNames[algorithm]} 未到达（${result.reason}）。没有路和策略撞墙是不同问题。`,!result.success);
  }catch(error){notice(error.message,true);}finally{busy=false;}
}
function showFrame(index) {
  if(!route) return;path=route.path.slice(0,index+1);costs=[0];
  for(const [r,c] of path.slice(1)) costs.push(costs[costs.length-1]+(/[2-9]/.test(grid[r][c])?Number(grid[r][c]):1));
  renderMap();$('frame').value=index;$('frame-label').textContent=`${index} / ${route.path.length-1}`;
}
function invalidatePrediction(){recognitionVersion++;prediction=null;$('execute').disabled=true;}
function drawPixel(index,value){pixels[index]=value; const node=$('pad').children[index];node.classList.toggle('on',!!value);node.setAttribute('aria-pressed',String(!!value));invalidatePrediction();}
function initPad(){for(let i=0;i<25;i++){const button=document.createElement('button');button.type='button';button.className='pixel';button.setAttribute('aria-label',`画板第${Math.floor(i/5)+1}行第${i%5+1}列`);button.setAttribute('aria-pressed','false');
  button.addEventListener('pointerdown',e=>{e.preventDefault();draw=true;paint=pixels[i]?0:1;drawPixel(i,paint);});
  button.addEventListener('pointerenter',()=>{if(draw)drawPixel(i,paint);});
  button.addEventListener('click',e=>{if(e.detail===0)drawPixel(i,pixels[i]?0:1);});$('pad').append(button);
}document.addEventListener('pointerup',()=>draw=false);document.addEventListener('pointercancel',()=>draw=false);}
function renderSamples(){const counts=Object.fromEntries(Object.keys(names).map(label=>[label,train.filter(s=>s.label===label).length]));
  $('sample-count').textContent=`训练 ${train.length}（上${counts.up} 右${counts.right} 下${counts.down} 左${counts.left}）· 测试 ${test.length}`;
  $('samples').replaceChildren();for(const [type,set] of [['训练',train],['测试',test]])set.forEach((sample,index)=>{const button=document.createElement('button');button.textContent=`${type}${index+1} ${names[sample.label]} ×`;button.title='删除这个样本';button.addEventListener('click',()=>{set.splice(index,1);dataVersion++;invalidatePrediction();renderSamples();$('evaluation').replaceChildren();});$('samples').append(button);});
}
function addSample(toTest){if(!pixels.some(Boolean))return notice('先在画板画一个非空符号。',true);const set=toTest?test:train;
  if(set.length>=160)return notice('每个集合最多 160 个样本。',true);
  if([...train,...test].some(s=>s.pixels.every((p,i)=>p===pixels[i])))return notice('这张图已存在。测试请独立重画，不能复制训练图。',true);
  set.push({label:$('label').value,pixels:pixels.slice()});dataVersion++;invalidatePrediction();renderSamples();$('evaluation').replaceChildren();notice(toTest?'已留作测试，不会用于分类训练。':'已保存标注样本。还需要覆盖四个方向。');
}
async function recognize(){const version=++recognitionVersion;const dv=dataVersion;$('execute').disabled=true;prediction=null;
  try{const result=await api('/api/classify',{train,pixels,k:Number($('k').value)});if(version!==recognitionVersion||dv!==dataVersion)return;
    prediction=result.label;$('execute').disabled=!result.label;
    $('prediction').textContent=result.label?`预测：${names[result.label]}。最近距离 ${result.distance.toFixed(2)}，近邻票数占比 ${(result.vote_share*100).toFixed(0)}%（不是概率）。确认后才移动。`:`暂不判断：${result.reason}。尝试补充独立样本；不要强行猜一个方向。`;
  }catch(error){$('prediction').textContent=error.message;notice(error.message,true);}
}
async function assess(){const version=dataVersion;$('evaluation').textContent='评测当前留出集…';
  try{const report=await api('/api/evaluate',{train,test,k:Number($('k').value)});if(version!==dataVersion)return;
    $('evaluation').replaceChildren();const p=document.createElement('p');p.textContent=`当前留出集 ${report.n_test} 条：准确率 ${(report.accuracy*100).toFixed(1)}%，可判断比例 ${(report.coverage*100).toFixed(1)}%。仅反映这批小样本。`;$('evaluation').append(p);
    const list=document.createElement('pre');list.textContent=report.results.map((r,i)=>`${i+1}. 标注${names[r.expected]} → ${names[r.label]||'拒识'}`).join('\n');$('evaluation').append(list);
  }catch(error){$('evaluation').textContent=error.message;notice(error.message,true);}
}
function exportRun(){const data={schema:1,grid,train,test,comparisons,note:'仅本机实验记录，不是教师评分；无学生姓名。'};const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download='robot-lab-experiment.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('已导出地图、样本和策略结果。请另附你的预测、改动与失败分析。');}
async function init(){initPad();
  const response=await fetch('/api/presets');if(!response.ok)throw Error('无法载入关卡');const data=await response.json();maps=data.maps;demoTrain=data.train;
  maps.forEach((map,i)=>{const button=document.createElement('button');button.className=i===0?'active':'';button.textContent=map.title;const small=document.createElement('small');small.textContent=`挑战 0${i+1}`;button.prepend(small);button.addEventListener('click',()=>{if(busy)return;setMap(map.grid,map.title,map.question);[...$('presets').children].forEach(b=>b.classList.toggle('active',b===button));notice('挑战已切换。先预测哪条路线更好。');});$('presets').append(button);});
  setMap(maps[0].grid,maps[0].title,maps[0].question);notice('先手动送达，再比较 BFS 与最低能耗；右侧可以训练自己的手绘控制器。');
  document.querySelectorAll('[data-move]').forEach(b=>b.addEventListener('click',()=>move(b.dataset.move)));
  $('reset').addEventListener('click',()=>{if(!busy)reset();});
  for(const key of ['bfs','dijkstra','student'])$(key).addEventListener('click',()=>run(key));
  document.querySelectorAll('[data-brush]').forEach(b=>b.addEventListener('click',()=>{if(busy)return;brush=b.dataset.brush;document.querySelectorAll('[data-brush]').forEach(other=>other.setAttribute('aria-pressed',String(other===b)));notice(brush==='play'?'已返回探索模式。':'点格子修改地图；请保留唯一的起点和终点。');}));
  $('apply-map').addEventListener('click',async()=>{if(busy)return;busy=true;const rows=$('map-text').value.trim().split(/\r?\n/);try{await api('/api/solve',{grid:rows});setMap(rows);notice('新关卡已应用。现在交换给同学试试。');}catch(error){notice(error.message,true);}finally{busy=false;}});
  $('frame').addEventListener('input',()=>{stop();showFrame(Number($('frame').value));});
  $('play').addEventListener('click',()=>{if(timer){stop();return;}if(!route)return;if(Number($('frame').value)>=route.path.length-1)showFrame(0);$('play').textContent='暂停';const delay=matchMedia('(prefers-reduced-motion: reduce)').matches?600:200;timer=setInterval(()=>{const next=Number($('frame').value)+1;if(next>=route.path.length){stop();return;}showFrame(next);},delay);});
  $('clear-pad').addEventListener('click',()=>pixels.forEach((_,i)=>drawPixel(i,0)));
  $('add-train').addEventListener('click',()=>addSample(false));$('add-test').addEventListener('click',()=>addSample(true));
  $('demo-data').addEventListener('click',()=>{train=clone(demoTrain);test=[];dataVersion++;invalidatePrediction();renderSamples();$('evaluation').replaceChildren();notice('已载入 4 个明确标记的合成样本（不是你的数据）。请独立画测试符号。');});
  $('clear-data').addEventListener('click',()=>{train=[];test=[];dataVersion++;invalidatePrediction();renderSamples();$('evaluation').replaceChildren();notice('样本已清空，可从自己的符号重新开始。');});
  $('k').addEventListener('change',()=>{dataVersion++;invalidatePrediction();$('evaluation').replaceChildren();});
  $('recognize').addEventListener('click',recognize);$('evaluate').addEventListener('click',assess);
  $('execute').addEventListener('click',()=>{if(prediction){const direction=prediction;invalidatePrediction();move(direction);}});$('export').addEventListener('click',exportRun);
  document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey||e.repeat||e.target.closest('input,textarea,select,button,summary,a'))return;const key={ArrowUp:'up',ArrowRight:'right',ArrowDown:'down',ArrowLeft:'left',w:'up',d:'right',s:'down',a:'left'}[e.key];if(key){e.preventDefault();move(key);}});
}
init().catch(error=>notice(error.message,true));
