"use strict";
const data=JSON.parse(document.querySelector('#corp-data').textContent);
const $=s=>document.querySelector(s);
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
const localUrl=p=>{const s=String(p).replaceAll('\\','/');return 'file:///'+s.split('/').map((part,i)=>i===0&&part.endsWith(':')?part:encodeURIComponent(part)).join('/')};
const safeUrl=p=>{try{const u=new URL(p);return ['http:','https:','file:'].includes(u.protocol)?u.href:null}catch{return null}};
function link(label,target,cls=''){const a=el('a',cls,label);const url=/^[A-Za-z]:[\\/]/.test(target)?localUrl(target):safeUrl(target);if(url){a.href=url;a.target='_blank';a.rel='noopener noreferrer'}else{a.removeAttribute('href')}return a}
const projects=data.inventory.projects;
const taskLabels={ready:'Готово к работе',in_progress:'В работе',review:'На вашей проверке',done:'Принято владельцем',blocked:'Ожидает зависимости'};
function switchView(id){document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!==id);document.querySelectorAll('.nav').forEach(n=>{n.classList.toggle('active',n.dataset.view===id);n.setAttribute('aria-current',n.dataset.view===id?'page':'false')});window.scrollTo({top:0,behavior:'instant'})}
document.querySelectorAll('.nav').forEach(n=>n.addEventListener('click',()=>switchView(n.dataset.view)));
$('.signature').addEventListener('click',e=>{e.preventDefault();switchView('home')});
$('#date').textContent=new Date(data.built_at).toLocaleString('ru-RU',{day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'});
const countLocal=projects.filter(p=>p.path).length;
const countAvailable=projects.filter(p=>p.folder_available_now===true).length;
const values=[[projects.length,'проектов в реестре'],[data.inventory.github.length,'репозиториев GitHub'],[`${countAvailable} / ${countLocal}`,'локальных папок доступны'],[data.tasks.filter(t=>t.status==='review').length,'на вашей проверке']];
values.forEach(([num,label])=>{const n=el('div','stat');n.append(el('b','',String(num)),el('span','',label));$('#stats').append(n)});
$('#focus-title').textContent=data.next?.title||'Оценить подготовленные результаты';
$('#focus-criteria').textContent=data.next?.acceptance||'Открыть материал и оставить короткое замечание.';
const pilot=data.config.resources.find(r=>r.kind==='pilot');
$('#pilot-open').disabled=!pilot;
$('#pilot-open').addEventListener('click',()=>{if(pilot)window.open(localUrl(pilot.path),'_blank','noopener')});
const resume=`Продолжи Personal Corp 3 из ${data.runtime.root}. Прочитай AGENTS.md, выполни ${data.runtime.command} daily. Используй существующий реестр портфеля, сохрани доказательство результата и обнови очередь. Не присваивай мою приёмку автоматически.`;
$('#resume').textContent=resume;
$('#update-command').textContent=data.runtime.command+' dashboard';
$('#copy-brief').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(resume);$('#copy-status').textContent='Поручение скопировано. Вставьте его в следующий чат.'}catch{$('#copy-status').textContent='Скопируйте поручение в разделе «Как это работает».'}});
$('#source-note').textContent=`Обзор портфеля: ${data.inventory.portfolio_checked_at}. Наличие папок проверено при импорте: ${data.inventory.generated_at}. ${data.inventory.scope}`;
function details(p){const host=$('#dialog-content');host.replaceChildren();host.append(el('h2','',p.label),el('p','path',p.path||'Облачный проект — локальный путь отсутствует'),el('p','',p.stage||'Этап неизвестен'));
 const obs=data.observations.filter(o=>o.projectId===p.projectId);
 if(obs.length){host.append(el('h3','','Дополнительная проверка штаба'));obs.forEach(o=>{host.append(el('p','',`${o.at}: ${o.text}`));if(o.source)host.append(link('Основание ↗',o.source,'evidence'))})}
 host.append(el('h3','','Ближайшие цели из обзора'));const ul=el('ol');(p.next_goals_proposed||['Требуется уточнить актуальную задачу.']).forEach(t=>ul.append(el('li','',t)));host.append(ul);
 if(p.paused_scopes?.length){host.append(el('h3','','Сохранённые ограничения'));p.paused_scopes.forEach(t=>host.append(el('p','',typeof t==='string'?t:JSON.stringify(t))))}
 host.append(el('h3','','Источники'));(p.sources||[]).forEach(s=>{const target=s.path||s.url;if(target)host.append(link(target,target,'evidence'))});host.append(el('p','fine','Проверка приложения не запускалась при импорте. Перед изменениями прочитайте его актуальные правила и продолжение.'));$('#project-dialog').showModal()}
$('#close-dialog').addEventListener('click',()=>$('#project-dialog').close());
$('#project-dialog').addEventListener('click',e=>{if(e.target===$('#project-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close()}});
function renderProjects(){const term=$('#search').value.toLocaleLowerCase('ru');const mode=$('#availability').value;const found=projects.filter(p=>{const text=[p.label,p.path,p.stage,p.decision].join(' ').toLocaleLowerCase('ru');return text.includes(term)&&(mode==='all'||mode==='local'&&p.folder_available_now===true||mode==='missing'&&p.folder_available_now===false||mode==='cloud'&&!p.path)});const list=$('#project-list');list.replaceChildren();$('#project-count').textContent=`Показано ${found.length} из ${projects.length}`;found.forEach(p=>{const card=el('button','project-card');const available=p.folder_available_now;card.append(el('span',available===false?'tag warning':'tag',!p.path?'Облачный':available?'Папка доступна':'Папка не найдена'),el('h3','',p.label),el('p','',p.stage||'Этап неизвестен'),el('span','path',p.path||'ChatGPT · облачный проект'));card.addEventListener('click',()=>details(p));list.append(card)});if(!found.length)list.append(el('p','empty','Проектов по этому запросу нет. Измените поиск или фильтр.'))}
$('#search').addEventListener('input',renderProjects);$('#availability').addEventListener('change',renderProjects);renderProjects();
data.inventory.github.forEach(r=>$('#repos').append(link(`${r.name} · ${r.visibility==='PRIVATE'?'закрытый':'публичный'}`,r.url)));
for(const status of ['in_progress','ready','review','blocked','done']){const tasks=data.tasks.filter(t=>t.status===status);if(!tasks.length)continue;const group=el('section','task-group');group.append(el('h2','',`${taskLabels[status]} · ${tasks.length}`));tasks.forEach(t=>{const card=el('article','task-card');card.append(el('div','task-meta',`${t.id} / ${t.department} / ${t.assignee==='owner'?'владелец':'агент'} / приоритет ${t.priority}`),el('h3','',t.title),el('p','',t.acceptance));if(t.history?.at(-1)?.note)card.append(el('p','fine',t.history.at(-1).note));t.evidence?.forEach(p=>card.append(link('Открыть результат ↗',p,'evidence')));group.append(card)});$('#task-list').append(group)}
data.config.resources.forEach(r=>$('#resources').append(link(r.label,r.path||r.url)));
