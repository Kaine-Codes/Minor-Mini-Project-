const $=id=>document.getElementById(id), root=document.documentElement;
const COLORS={temp:'error',hum:'secondary',gas:'tertiary-fixed-dim'};
const LIMITS={1:1000,6:3000,24:5000,168:8000};
let timers=[],hist=[],win=1,cmds={led:0,fan:0},last=null,trend=null;
let thr={temp:46,gas:2300,lux:3000};
try{Object.assign(thr,JSON.parse(localStorage.getItem('aria-thr')||'{}'))}catch(e){}

/* ---------- theme ---------- */
function setTheme(t){
  root.classList.toggle('light',t==='light');root.classList.toggle('dark',t!=='light');
  const l=t==='light';
  $('theme-icon').textContent=l?'light_mode':'dark_mode';$('theme-label').textContent=l?'Light Mode':'Dark';
  $('login-theme-icon').textContent=l?'dark_mode':'light_mode';
  try{localStorage.setItem('aria-theme',t)}catch(e){}
  if(hist.length)drawChart();
}
const flip=()=>setTheme(root.classList.contains('light')?'dark':'light');
$('theme-toggle-btn').onclick=flip;$('login-theme').onclick=flip;

/* ---------- api ---------- */
async function api(url,opt){
  const r=await fetch(url,Object.assign({credentials:'same-origin',headers:{'Content-Type':'application/json'}},opt));
  if(r.status===401&&url!=='/api/login'){showLogin();throw new Error('unauthorized')}
  return r;
}
function showLogin(){
  timers.forEach(clearInterval);timers=[];
  $('app').classList.add('hidden');$('login').classList.remove('hidden');$('username').focus();
}
function showApp(){
  $('login').classList.add('hidden');$('app').classList.remove('hidden');
  $('foot-host').textContent='HOST: '+location.host;
  initSliders();refresh();loadCmds();loadHist();
  timers=[setInterval(refresh,3000),setInterval(loadCmds,5000),setInterval(loadHist,15000),setInterval(tick,1000)];
  tick();
}
function tick(){$('clock').textContent=new Date().toLocaleTimeString([],{hour12:false,timeZoneName:'short'})}

$('authForm').onsubmit=async e=>{
  e.preventDefault();$('le').textContent='';$('submitBtn').disabled=true;
  try{
    const r=await api('/api/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});
    if(r.ok){$('password').value='';showApp()}else $('le').textContent='Incorrect username or password.';
  }catch(e){$('le').textContent='Cannot reach the ARIA server. Check your connection.'}
  $('submitBtn').disabled=false;
};
$('logout').onclick=async e=>{e.preventDefault();await fetch('/api/logout',{method:'POST',credentials:'same-origin'});showLogin()};

/* ---------- helpers ---------- */
const BADGE='text-[11px] font-medium px-2 py-0.5 rounded-full ';
const TONE={ok:'text-tertiary bg-surface-container-highest',bad:'text-error bg-error-container/30',warn:'text-amber-300 bg-amber-400/20',dim:'text-on-surface-variant bg-surface-container-highest'};
function badge(id,text,tone){const e=$(id);e.textContent=text;e.className=BADGE+TONE[tone]}
const pct=(v,m)=>Math.max(0,Math.min(100,(v/m)*100))+'%';
const f1=v=>v==null?'--':Number(v).toFixed(1);

/* ---------- live readings ---------- */
async function refresh(){
  try{
    const d=await (await api('/api/readings/latest')).json();
    if(!d.timestamp){paintLive(false,null);return}
    last=d;paintReading();
  }catch(e){}
}
function paintReading(){
  const d=last;if(!d)return;
  const age=(Date.now()-Date.parse(d.timestamp))/1000,live=age<30;
  const gasAlert=!!d.local_gas_override||d.gas_raw>=thr.gas,hot=d.temperature>=thr.temp;
  $('val-temp').textContent=f1(d.temperature);$('bar-temp').style.width=pct(d.temperature,50);
  $('val-humidity').textContent=f1(d.humidity);$('bar-hum').style.width=pct(d.humidity,100);
  $('val-gas').textContent=d.gas_raw??'--';$('bar-gas').style.width=pct(d.gas_raw,4095);
  $('val-lux').textContent=d.light_raw??'--';$('lux-progress-bar').style.width=pct(d.light_raw,4095);
  if(hot)badge('badge-temp','High','bad');else if(trend==null)badge('badge-temp','--','dim');
  else badge('badge-temp',Math.abs(trend)<0.1?'Stable':(trend>0?'+':'')+trend.toFixed(1)+'°C/hr',trend>=1?'bad':'dim');
  badge('badge-hum',d.humidity<30?'Dry':d.humidity>70?'Humid':'Optimal',d.humidity<30||d.humidity>70?'warn':'ok');
  badge('badge-gas',gasAlert?'Alert':'Clear',gasAlert?'bad':'ok');
  const lx=d.light_raw;badge('badge-lux-state',lx>=thr.lux?'Bright':lx>=thr.lux/4?'Indoor':'Dark',lx>=thr.lux?'warn':'dim');
  const m=$('motion-state-label');m.textContent=d.motion?'Occupant Present':'Zone Vacant';
  m.className='text-[20px] font-semibold flex items-center gap-space-xs '+(d.motion?'text-primary':'text-on-surface-variant');
  $('motion-sub').textContent=d.motion?'Motion detected':'No motion detected';
  $('motion-dot').classList.toggle('opacity-0',!d.motion);
  const o=$('occupant-entity');o.classList.toggle('opacity-0',!d.motion);o.classList.toggle('scale-75',!d.motion);o.classList.toggle('opacity-100',!!d.motion);o.classList.toggle('scale-100',!!d.motion);
  $('occ-label').textContent=d.motion?'Occupant Detected':'Zone Vacant';
  const v=$('vib-label');v.textContent=d.vibration?'Vibration Detected':'Stable';
  v.className='text-[20px] font-semibold '+(d.vibration?'text-error':'text-secondary-fixed');
  $('vib-sub').textContent=d.vibration?'Impact sensed':'No vibration';badge('badge-vib',d.vibration?'Alert':'Normal',d.vibration?'bad':'dim');
  $('twin-hum').textContent=f1(d.humidity)+'% RH';
  $('tile-temp').textContent=f1(d.temperature)+'°C '+(hot?'High':'Normal');
  $('tile-gas').textContent=gasAlert?'Alert':'Clear';
  paintLive(live,age,gasAlert);paintCmds();
}
function paintLive(live,age,gasAlert){
  $('live-dot').className='w-1.5 h-1.5 rounded-full '+(live?'bg-tertiary-fixed-dim animate-pulse':'bg-error');
  $('live-text').textContent=live?'LIVE':'OFFLINE';
  $('tile-mesh').textContent=live?'Online':'Offline';
  const c=$('status-conn');c.textContent=live?'Connected':'Disconnected';c.className=(live?'text-tertiary':'text-error')+' font-medium';
  $('status-msg').textContent=age==null?'Waiting for the first reading':!live?'No data from the ESP32 for '+(age<120?Math.round(age)+' s':Math.round(age/60)+' min'):gasAlert?'Gas alert • The device has taken local control':'All systems nominal • Telemetry updated in real-time';
  if(last)$('foot-update').textContent='LAST UPDATE '+new Date(last.timestamp).toLocaleTimeString([],{hour12:false});
}

/* ---------- actuators ---------- */
async function loadCmds(){try{cmds=await (await api('/api/commands')).json();paintCmds()}catch(e){}}
async function send(p){
  Object.assign(cmds,p);paintCmds();
  try{const r=await api('/api/commands',{method:'POST',body:JSON.stringify(p)});if(!r.ok)throw 0}catch(e){loadCmds()}
}
$('toggle-light-btn').onclick=()=>send({led:!cmds.led});
$('toggle-fan-btn').onclick=()=>send({fan:!cmds.fan});
function triggerPreset(t){send(t==='away'?{led:false,fan:false}:{fan:true})}
function sw(btn,thumb,on){
  thumb.classList.toggle('translate-x-6',on);thumb.classList.toggle('translate-x-0',!on);
  btn.classList.toggle('bg-primary-container',on);btn.classList.toggle('bg-surface-container-highest',!on);
  btn.classList.toggle('shadow-[0_0_12px_rgba(0,240,255,0.4)]',on);btn.setAttribute('aria-pressed',on);
}
function paintCmds(){
  const led=!!cmds.led,fan=!!cmds.fan,lx=last?last.light_raw:'--';
  sw($('toggle-light-btn'),$('toggle-light-thumb'),led);sw($('toggle-fan-btn'),$('toggle-fan-thumb'),fan);
  $('light-status-text').textContent=led?'RELAY 1: ON • LIGHT '+lx:'RELAY 1: OFF • STANDBY';
  $('light-status-text').className='font-label-code text-label-code '+(led?'text-amber-300':'text-on-surface-variant');
  $('icon-light-box').className='w-12 h-12 rounded-xl flex items-center justify-center transition-all '+(led?'bg-amber-500/20 text-amber-300 shadow-[0_0_16px_rgba(245,158,11,0.4)]':'bg-surface-container-high text-on-surface-variant');
  $('room-lighting-aura').style.opacity=led?'0.8':'0';$('room-ambient-darkness').style.opacity=led?'0':'0.7';
  $('ceiling-lamp-node').className='w-8 h-8 rounded-full flex items-center justify-center '+(led?'bg-amber-400/90 shadow-[0_0_24px_rgba(251,191,36,0.8)] text-on-surface':'bg-surface-container-highest text-on-surface-variant shadow-none');
  $('light-twin-tag').textContent=led?'LIGHT ON ('+lx+' RAW)':'LIGHT OFF';
  $('light-twin-tag').className='px-2 py-0.5 rounded bg-surface-container/80 font-label-code text-label-code '+(led?'text-amber-300':'text-on-surface-variant');
  $('fan-status-text').textContent=fan?'RELAY 2: ACTIVE':'RELAY 2: STOPPED';
  $('fan-status-text').className='font-label-code text-label-code '+(fan?'text-secondary':'text-on-surface-variant');
  $('icon-fan-box').className='w-12 h-12 rounded-xl flex items-center justify-center transition-all '+(fan?'bg-secondary-fixed/20 text-secondary shadow-[0_0_16px_rgba(76,215,246,0.3)]':'bg-surface-container-high text-on-surface-variant');
  $('icon-fan-box').firstElementChild.classList.toggle('animate-[spin_2s_linear_infinite]',fan);
  $('digital-fan-blades').classList.toggle('animate-[spin_0.45s_linear_infinite]',fan);
  $('fan-wind-aura').classList.toggle('opacity-0',!fan);
  $('fan-twin-label').textContent=fan?'FAN ON':'FAN OFF';$('tile-vent').textContent=fan?'Active':'Standby';
}

/* ---------- thresholds (dashboard alerts only) ---------- */
function initSliders(){
  [['temp','slider-temp-thresh','disp-temp-thresh','°C'],['gas','slider-gas-thresh','disp-gas-thresh',' RAW'],['lux','slider-lux-thresh','disp-lux-thresh',' RAW']].forEach(([k,s,d,u])=>{
    const el=$(s);el.value=thr[k];$(d).textContent=thr[k]+u;
    el.oninput=()=>{thr[k]=+el.value;$(d).textContent=el.value+u;try{localStorage.setItem('aria-thr',JSON.stringify(thr))}catch(e){};paintReading()};
  });
}

/* ---------- chart ---------- */
async function loadHist(){
  try{hist=await (await api('/api/readings/history?limit='+LIMITS[win])).json();
    hist.forEach(p=>p._t=Date.parse(p.timestamp));
    const hr=hist.filter(p=>p._t>Date.now()-3600e3&&p.temperature!=null);
    trend=null;
    if(hr.length>1){const a=hr[0],b=hr[hr.length-1],dt=(b._t-a._t)/3600e3;if(dt>0.02)trend=(b.temperature-a.temperature)/dt}
    drawChart();if(last)paintReading();
  }catch(e){}
}
document.querySelectorAll('[data-win]').forEach(b=>b.onclick=()=>{win=+b.dataset.win;
  document.querySelectorAll('[data-win]').forEach(x=>{const on=x===b;x.classList.toggle('bg-primary-container',on);x.classList.toggle('text-on-primary-container',on);x.classList.toggle('font-semibold',on);x.classList.toggle('text-on-surface-variant',!on)});
  loadHist()});
const col=n=>'rgb('+getComputedStyle(root).getPropertyValue('--c-'+n).trim()+')';
let view=[];
function windowed(){const t1=Date.now();return hist.filter(p=>p._t>=t1-win*3600e3)}
function drawChart(){
  view=windowed();const svg=$('chart-svg');
  const yl=$('ylabels');yl.innerHTML=[4,3,2,1,0].map(i=>{const f=i/4;return '<div class="w-full '+(i?'border-b border-surface-variant ':'')+'flex justify-between text-[10px] font-label-code"><span>'+(i?Math.round(50*f)+'°C / '+Math.round(100*f)+'% / '+Math.round(4095*f)+' RAW':'')+'</span></div>'}).join('');
  if(view.length<2){svg.innerHTML='';$('xlabels').innerHTML='<span>Waiting for more readings in this window…</span>';return}
  const t0=view[0]._t,t1=view[view.length-1]._t,span=Math.max(1,t1-t0),step=Math.ceil(view.length/300);
  const pts=view.filter((p,i)=>i%step===0||i===view.length-1);
  const S=[['temp','temperature',50,3,''],['hum','humidity',100,2.5,''],['gas','gas_raw',4095,2,'3,3']];
  let out='<defs>'+S.map(s=>'<linearGradient id="g-'+s[0]+'" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="'+col(COLORS[s[0]])+'" stop-opacity="0.28"/><stop offset="100%" stop-color="'+col(COLORS[s[0]])+'" stop-opacity="0"/></linearGradient>').join('')+'</defs>';
  [S[1],S[2],S[0]].forEach(([id,key,full,w,dash])=>{
    const q=pts.filter(p=>p[key]!=null&&!(p[key]===0&&id!=='gas'));if(q.length<2)return;
    const xy=q.map(p=>((p._t-t0)/span*1000).toFixed(1)+','+(240-Math.max(0,Math.min(1,p[key]/full))*240).toFixed(1));
    out+='<polygon fill="url(#g-'+id+')" points="'+xy.join(' ')+' 1000,240 0,240"/><polyline fill="none" stroke="'+col(COLORS[id])+'" stroke-width="'+w+'" '+(dash?'stroke-dasharray="'+dash+'" ':'')+'vector-effect="non-scaling-stroke" stroke-linejoin="round" points="'+xy.join(' ')+'"/>';
  });
  svg.innerHTML=out;
  const fmt=t=>new Date(t).toLocaleString([],win>6?{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}:{hour:'2-digit',minute:'2-digit',hour12:false});
  $('xlabels').innerHTML=[0,1,2,3,4,5].map(i=>i===5?'<span class="text-primary font-semibold">'+fmt(t1)+' (NOW)</span>':'<span>'+fmt(t0+span*i/5)+'</span>').join('');
}
const box=$('chart-box');
box.onmousemove=e=>{
  if(view.length<2)return;
  const r=box.getBoundingClientRect(),f=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
  const t=view[0]._t+f*(view[view.length-1]._t-view[0]._t);
  let b=view[0];for(const p of view)if(Math.abs(p._t-t)<Math.abs(b._t-t))b=p;
  const s=$('scrub');s.classList.remove('hidden');s.style.left=f*100+'%';
  $('scrub-tip').style.transform=f>0.75?'translateX(-45%)':f<0.25?'translateX(45%)':'none';
  $('scrub-txt').textContent=new Date(b._t).toLocaleTimeString([],{hour12:false})+' // Temp '+f1(b.temperature)+'°C • Hum '+f1(b.humidity)+'% • Gas '+(b.gas_raw??'--');
};
box.onmouseleave=()=>$('scrub').classList.add('hidden');
function exportCsv(){
  const cols=['timestamp','temperature','humidity','gas_raw','light_raw','motion','vibration','local_gas_override'];
  const rows=[cols.join(',')].concat((view.length?view:hist).map(p=>cols.map(c=>p[c]??'').join(',')));
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'}));
  a.download='aria-telemetry.csv';a.click();URL.revokeObjectURL(a.href);
}

/* ---------- section nav (scroll-spy) ---------- */
const SECS=['overview','sensors','controls','telemetry'];
function spy(){
  let cur=SECS[0];
  for(const s of SECS){const el=$(s);if(el&&el.getBoundingClientRect().top<=140)cur=s}
  if(innerHeight+scrollY>=document.documentElement.scrollHeight-4)cur=SECS[SECS.length-1];
  document.querySelectorAll('[data-sec]').forEach(a=>{
    const on=a.dataset.sec===cur,bottom=!!a.closest('#nav-bottom');
    if(bottom){a.classList.toggle('text-primary',on);a.classList.toggle('text-on-surface-variant',!on)}
    else{['bg-primary-container','text-on-primary-container','font-medium'].forEach(c=>a.classList.toggle(c,on));a.classList.toggle('text-on-surface-variant',!on)}
    on?a.setAttribute('aria-current','true'):a.removeAttribute('aria-current');
  });
}
addEventListener('scroll',spy,{passive:true});addEventListener('resize',spy);
document.querySelectorAll('[data-sec]').forEach(a=>a.onclick=e=>{e.preventDefault();$(a.dataset.sec).scrollIntoView({behavior:'smooth',block:'start'})});
setInterval(spy,1500);

/* ---------- start ---------- */
setTheme(root.classList.contains('light')?'light':'dark');
(async()=>{try{const s=await (await fetch('/api/status',{credentials:'same-origin'})).json();s.logged_in?showApp():showLogin()}catch(e){showLogin()}})();
