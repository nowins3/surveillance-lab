'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let credential = null, state = null, connected = false, streamAbort = null, clockOffset = 0;
let feedURL = null, lastFrame = -1, captureStream = null, source = 'off', sourceGeneration = 0;
let people = 2, lastSimulation = 0, toastTimer = null, health = {vision:false};
let roundSignature = '', scenarioSignature = '', historySignature = '', logSignature = '', settingsSignature = '';
const base = () => `/api/rooms/${credential.code}`;
const auth = () => ({Authorization:`Bearer ${credential.token}`});
const serverNow = () => Date.now()/1000 + clockOffset;
function toast(message, error=false){ $('toast').textContent = message; $('toast').className=error?'error':''; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,5000); }
async function api(path, data, method){
  const response = await fetch(path,{method:method || (data ? 'POST':'GET'),headers:{...(credential?auth():{}),...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined});
  let result; try{result=await response.json();}catch{throw new Error(`The server returned ${response.status}.`);}
  if(!response.ok)throw new Error(result.error || 'The request failed.');
  return result;
}
async function control(action, data={}){return api(base()+'/control',{action,...data});}
function guard(fn){return async event=>{try{await fn(event);}catch(error){toast(error.message,true);}};}
function setConnection(ok){connected=ok; $('connection').textContent=ok?'CONNECTED':'RECONNECTING'; $('connection').className='badge '+(ok?'on':'warn'); roundSignature=''; if(state)renderRound();}
async function enter(data){
  credential=data; sessionStorage.setItem('surveillance-session',JSON.stringify(data));
  $('landing').hidden=true; $('workspace').hidden=false;
  const manager=data.role==='manager';
  for(const id of ['broadcastControls','managerScenarios','managerSettings','activityPanel','export'])$(id).hidden=!manager;
  $('copyLink').hidden=!manager;
  $('roleLabel').textContent=manager?'THE CONTROL ROOM':'THE OBSERVATION ROOM';
  state=await api(base()+'/state'); render(state); connect();
}
async function connect(){
  if(streamAbort)streamAbort.abort();
  const controller=new AbortController(); streamAbort=controller;
  while(!controller.signal.aborted && credential){
    try{
      const response=await fetch(base()+'/events',{headers:auth(),signal:controller.signal});
      if(!response.ok){
        if([401,404].includes(response.status)){reset();toast('This room is no longer available. Please join again.',true);return;}
        throw new Error('Connection unavailable');
      }
      setConnection(true);
      const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer='';
      while(true){
        const {done,value}=await reader.read(); if(done)break;
        buffer+=decoder.decode(value,{stream:true});
        let index;
        while((index=buffer.indexOf('\n\n'))>=0){
          const event=buffer.slice(0,index); buffer=buffer.slice(index+2);
          if(event.startsWith('data: '))render(JSON.parse(event.slice(6)));
        }
      }
    }catch(error){if(controller.signal.aborted)return;}
    if(!controller.signal.aborted){setConnection(false);await new Promise(resolve=>setTimeout(resolve,1500));}
  }
}
function render(next){
  state=next; clockOffset=state.serverTime-Date.now()/1000;
  $('sessionTitle').textContent=state.title; $('roomCode').textContent=state.code;
  $('participantCount').textContent=state.participants; $('onlineCount').textContent=`${state.online} online`;
  $('sourceLabel').textContent=state.live?(state.source==='demo'?'Simulation':'Camera'):'Standby';
  $('sourceDetail').textContent=state.live?'Shared frame broadcast · no audio':state.ended?'Session ended':'Waiting for a broadcast';
  $('roundCount').textContent=String(state.history.length).padStart(2,'0');
  $('liveBadge').textContent=state.live?(state.source==='demo'?'SIMULATED':'LIVE'):'STANDBY';
  $('liveBadge').className='badge '+(state.live?'on':'');
  $('simulationTag').hidden=state.source!=='demo'||!state.live;
  $('endedBanner').hidden=!state.ended;
  $('engineLabel').textContent=state.ended?'Stopped':state.settings.automatic?(state.settings.visionTriggers?'Timer + vision':'Periodic'):state.settings.visionTriggers?'Detection':'Manual';
  $('engineDetail').textContent=state.settings.automatic?`Next round after a ${state.settings.interval}s interval`:state.settings.visionTriggers?'Two detections + cooldown':'Manager controlled';
  if(!state.live){$('feed').hidden=true; $('feedPlaceholder').hidden=false;clearOverlay();}
  if(state.ended)stopCapture();
  const obs=state.observation;
  if(obs){
    $('observationTitle').textContent=`${obs.people} ${obs.people===1?'person':'people'} ${obs.simulated?'simulated':'detected'}${obs.zone?' · central zone occupied':''}`;
    $('observationDetail').textContent=`${obs.model} · frame #${obs.frameSeq} · ${new Date(obs.at*1000).toLocaleTimeString()}${obs.simulated?' · not model output':' · HOG scores are margins, not probabilities'}`;
  }else{
    $('observationTitle').textContent=state.live&&state.source==='camera'&&!health.vision?'Camera live · vision disabled':'No current observation';
    $('observationDetail').textContent='A model label is an observation, not a conclusion.';
  }
  renderRound(); renderHistory();
  if(state.role==='manager'){
    renderScenarios();renderLog();
    const sig=JSON.stringify(state.settings);
    if(sig!==settingsSignature){
      const form=$('settingsForm'); for(const [key,value]of Object.entries(state.settings)){const input=form.elements[key];if(input.type==='checkbox')input.checked=value;else input.value=value;}
      settingsSignature=sig;
    }
    for(const el of $('settingsForm').elements)el.disabled=state.ended;
    $('endSession').disabled=state.ended;
    $('demo').disabled=state.ended; $('camera').disabled=state.ended;
    $('stop').disabled=source==='off';
    $('toggleCustom').disabled=state.ended;
  }
}
function resultsHTML(options,counts,total){return options.map((option,i)=>`<div class="result-row"><div class="result-label"><span>${escapeHTML(option)}</span><span>${counts[i]} · ${total?Math.round(counts[i]/total*100):0}%</span></div><progress class="result-track" value="${counts[i]}" max="${Math.max(total,1)}" aria-label="${escapeHTML(option)}: ${counts[i]} of ${total}"></progress></div>`).join('');}
function renderRound(){
  if(!state)return;
  const round=state.round, manager=state.role==='manager';
  const signature=JSON.stringify([round,state.ended,connected,state.participants]);
  if(signature===roundSignature){updateTimer();return;}
  roundSignature=signature;
  if(!round){
    $('roundStatus').textContent=state.ended?'ENDED':'WAITING';
    $('roundContent').innerHTML=`<span class="waiting-icon">◎</span><h2 class="waiting-title">The next decision<br>is yours to make.</h2><p class="decision-copy">${manager?'Start a scenario below, or enable periodic prompts. Participants will receive the same question together.':'Watch the scene. When the manager starts a round, your choices will appear here.'}</p><div class="round-observation">You can observe the same event and reach different conclusions.</div>`;
    return;
  }
  const isOpen=round.status==='open'&&!state.ended&&round.deadline>serverNow();
  $('roundStatus').textContent=round.status==='revealed'?'REVEALED':isOpen?'VOTING OPEN':'VOTING CLOSED';
  $('roundStatus').className='badge '+(isOpen?'on':'');
  let html=`<span class="category">${escapeHTML(round.category)} · ${escapeHTML(round.origin)}</span><h2 class="waiting-title">${escapeHTML(round.title)}</h2><div class="round-observation">${escapeHTML(round.observation)}${round.evidence?`<br><small>Trigger context: ${escapeHTML(round.evidence.model)}, frame #${round.evidence.frameSeq}. This is not a frozen image.</small>`:''}</div><h3 class="round-question">${escapeHTML(round.question)}</h3>`;
  if(round.status==='revealed'){
    html+=resultsHTML(round.options,round.counts,round.responses);
    html+=`<div class="discussion"><span class="eyebrow">OPEN THE DISCUSSION</span><p>${escapeHTML(round.reveal)}</p></div>`;
  }else if(manager){
    html+=resultsHTML(round.options,round.counts,round.responses);
    html+='<p class="hint">Live counts are visible only to the manager until revealed.</p>';
  }else{
    html+='<div class="choices">'+round.options.map((option,i)=>`<button class="choice ${round.myVote===i?'selected':''}" data-choice="${i}" ${!isOpen||!connected?'disabled':''}><span class="letter">${String.fromCharCode(65+i)}</span><span>${escapeHTML(option)}${round.myVote===i?' ✓':''}</span></button>`).join('')+'</div>';
    html+=`<p class="hint">${round.myVote!==null?'Your choice is saved. You can change it while voting is open.':isOpen?'Choose your response. Group results stay hidden until revealed.':'Voting has closed. Waiting for the reveal.'}</p>`;
  }
  html+=`<div class="round-footer"><span>${round.responses} response${round.responses===1?'':'s'} / ${state.participants} joined</span><span class="timer" id="countdown"></span></div>`;
  if(manager&&!state.ended&&round.status!=='revealed')html+=`<div class="round-actions"><button class="secondary small" id="closeRound" ${!isOpen?'disabled':''}>Close voting</button><button class="primary small" id="revealRound">Reveal results</button></div>`;
  $('roundContent').innerHTML=html;
  document.querySelectorAll('[data-choice]').forEach(button=>button.onclick=guard(async()=>{await api(base()+'/vote',{roundId:round.id,choice:Number(button.dataset.choice)});}));
  if($('closeRound'))$('closeRound').onclick=guard(()=>control('close'));
  if($('revealRound'))$('revealRound').onclick=guard(()=>control('reveal'));
  updateTimer();
}
function updateTimer(){
  if(!$('countdown')||!state?.round)return;
  const round=state.round, seconds=Math.max(0,Math.ceil(round.deadline-serverNow()));
  $('countdown').textContent=round.status==='open'?`${seconds}s`:round.status==='revealed'?'Complete':'Closed';
  if(round.status==='open'&&seconds===0){
    document.querySelectorAll('[data-choice]').forEach(button=>button.disabled=true);
    if($('closeRound'))$('closeRound').disabled=true;
    $('roundStatus').textContent='VOTING CLOSED';
  }
}
function renderScenarios(){
  const blocked=state.ended||!!(state.round&&state.round.status!=='revealed');
  const signature=JSON.stringify([state.scenarios,blocked]);if(signature===scenarioSignature)return;scenarioSignature=signature;
  $('scenarioList').innerHTML=state.scenarios.map((s,i)=>`<div class="scenario-row"><span class="scenario-number">${String(i+1).padStart(2,'0')}</span><div class="scenario-info"><h3>${escapeHTML(s.title)}</h3><p>${escapeHTML(s.category)} · ${s.trigger==='manual'?'manual':s.trigger==='timer'?'timer or manual':`${escapeHTML(s.trigger)} detection or manual`}</p></div><button class="quiet small" data-scenario="${escapeHTML(s.id)}" ${blocked?'disabled':''}>Launch ↗</button></div>`).join('');
  document.querySelectorAll('[data-scenario]').forEach(button=>button.onclick=guard(()=>control('start',{scenarioId:button.dataset.scenario})));
}
function renderHistory(){
  const sig=JSON.stringify(state.history);if(sig===historySignature)return;historySignature=sig;
  $('history').innerHTML=state.history.length?state.history.slice().reverse().map(r=>`<details><summary>${escapeHTML(r.title)}<span>${r.responses} responses</span></summary><p>${escapeHTML(r.question)}</p>${resultsHTML(r.options,r.counts,r.responses)}<p>${escapeHTML(r.reveal)}</p></details>`).join(''):'<p class="empty">Revealed rounds will appear here.</p>';
}
function renderLog(){const sig=JSON.stringify(state.events);if(sig===logSignature)return;logSignature=sig;$('activity').innerHTML=state.events.slice(-12).reverse().map(e=>`<div><time>${new Date(e.at*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</time><span>${escapeHTML(e.text)}</span></div>`).join('');}
function clearOverlay(){const canvas=$('overlay');canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);}
function drawOverlay(){
  clearOverlay();
  if(!state?.live||$('feed').hidden)return;
  const canvas=$('overlay'),ctx=canvas.getContext('2d'),obs=state.observation;
  ctx.strokeStyle='#c4adff50';ctx.lineWidth=1;ctx.setLineDash([6,8]);ctx.strokeRect(960*.35,10,960*.30,520);ctx.setLineDash([]);
  ctx.font='12px monospace';ctx.fillStyle='#c4adff99';ctx.fillText('OBSERVATION ZONE',960*.35+10,44);
  if(!obs||serverNow()-obs.at>3)return;
  for(const box of obs.boxes){
    const [x,y,w,h]=box.box.map((n,i)=>n*(i%2===0?960:540));
    ctx.strokeStyle=obs.simulated?'#e8b46d':'#c4adff';ctx.lineWidth=2;ctx.strokeRect(x,y,w,h);
    const label=obs.simulated?'SIMULATED PERSON':`PERSON · ${box.score.toFixed(2)}`;
    ctx.fillStyle='#101020e8';ctx.fillRect(x,y-21,ctx.measureText(label).width+14,21);ctx.fillStyle=ctx.strokeStyle;ctx.fillText(label,x+6,y-6);
  }
}
async function pollFrame(){
  try{
    if(credential&&state&&!state.ended){
      const response=await fetch(base()+'/frame',{headers:auth()});
      if(response.status===200){
        const seq=Number(response.headers.get('X-Frame-Sequence'));
        if(seq!==lastFrame){
          const blob=await response.blob(),url=URL.createObjectURL(blob),previous=feedURL;feedURL=url;lastFrame=seq;
          $('feed').src=url;$('feed').hidden=false;$('feedPlaceholder').hidden=true;
          $('frameTime').textContent=new Date(Number(response.headers.get('X-Frame-Time'))*1000).toLocaleTimeString();
          if(previous)URL.revokeObjectURL(previous);
        }
      }else if(response.status===204){$('feed').hidden=true;$('feedPlaceholder').hidden=false;clearOverlay();}
      drawOverlay();
    }
  }catch{/* The event channel reports connection status. */}
  setTimeout(pollFrame,250);
}
function drawDemo(ctx){
  const w=960,h=540,t=Date.now()/1000;
  ctx.fillStyle='#1a1b36';ctx.fillRect(0,0,w,h);
  ctx.fillStyle='#242b4b';ctx.fillRect(0,0,w,h*.70);
  ctx.fillStyle='#343454';ctx.fillRect(0,h*.70,w,h*.30);
  ctx.strokeStyle='#9895c520';ctx.lineWidth=1;
  for(let x=-200;x<1200;x+=120){ctx.beginPath();ctx.moveTo(480+(x-480)*.3,h*.70);ctx.lineTo(x,h);ctx.stroke();}
  for(let y=380;y<540;y+=35){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
  // Abstract architecture; shapes are synthetic people, never real footage.
  ctx.fillStyle='#181c37';ctx.fillRect(650,90,155,288);ctx.strokeStyle='#6c68a2';ctx.strokeRect(650,90,155,288);
  ctx.fillStyle='#9a96c4';ctx.font='13px monospace';ctx.fillText('COMMON AREA / 01',35,75);
  ctx.fillStyle='#e8b46d';ctx.font='11px monospace';ctx.fillText('SYNTHETIC SCENE — NO LIVE CAMERA',35,95);
  for(let i=0;i<people;i++){
    const x=(.12+i*.13)*w+48,y=.26*h,bob=Math.sin(t*1.5+i)*2;
    ctx.fillStyle=['#b6a2da','#8cace0','#aaa0d4'][i%3];
    ctx.beginPath();ctx.ellipse(x,y+27+bob,18,21,0,0,Math.PI*2);ctx.fill();
    ctx.beginPath();ctx.roundRect(x-24,y+55+bob,48,112,14);ctx.fill();
    ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=13;ctx.lineCap='round';
    for(const direction of [-1,1]){ctx.beginPath();ctx.moveTo(x+direction*11,y+156);ctx.lineTo(x+direction*17,y+248);ctx.stroke();ctx.beginPath();ctx.moveTo(x+direction*22,y+75);ctx.lineTo(x+direction*35,y+153);ctx.stroke();}
    ctx.fillStyle='#070b1d40';ctx.beginPath();ctx.ellipse(x,410,44,9,0,0,Math.PI*2);ctx.fill();
  }
  ctx.fillStyle='#ccc6eb88';ctx.font='12px monospace';ctx.fillText(new Date().toLocaleTimeString(),840,515);
}
function stopCapture(){
  source='off';sourceGeneration++;
  if(captureStream){captureStream.getTracks().forEach(track=>track.stop());captureStream=null;}
  $('captureVideo').srcObject=null;$('demoControls').hidden=true;$('stop').disabled=true;
  $('cameraHint').textContent='Share the camera on this device with everyone in the room. No audio is captured.';
}
async function startSource(next){
  if(credential?.role!=='manager'||state?.ended)return;
  stopCapture();
  const generation=sourceGeneration;
  try{
    if(next==='camera'){
      $('cameraHint').textContent='Allow camera access in your browser to broadcast from this device.';
      if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia)throw new Error('Camera access on this device requires HTTPS (or localhost on the server computer). Open this site over HTTPS, then click Share camera.');
      const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:960},height:{ideal:540}},audio:false});
      if(generation!==sourceGeneration){stream.getTracks().forEach(track=>track.stop());return;}
      captureStream=stream;$('captureVideo').srcObject=captureStream;await $('captureVideo').play();
      if(generation!==sourceGeneration)return;
      captureStream.getVideoTracks()[0].onended=()=>{stopCapture();control('source',{source:'off'}).catch(()=>{});toast('Camera sharing stopped.');};
    }
    await control('source',{source:next});
  }catch(error){
    if(generation!==sourceGeneration)return;
    stopCapture();
    const message=next==='camera'?({
      NotAllowedError:'Camera permission was denied. Allow camera access for this site, then click Share camera.',
      NotFoundError:'No camera was found on this device. Connect or enable a camera, then click Share camera.',
      NotReadableError:'This device camera is unavailable or in use. Close other camera apps, then click Share camera.'
    }[error.name]||error.message):error.message;
    if(next==='camera')$('cameraHint').textContent=message;
    throw new Error(message);
  }
  if(generation!==sourceGeneration)return;
  source=next;$('demoControls').hidden=next!=='demo';$('stop').disabled=false;lastSimulation=0;
  if(next==='camera')$('cameraHint').textContent='Broadcasting this device camera to the room. Keep this page open. Use Stop broadcast to turn it off.';
  captureLoop(generation);
}
async function captureLoop(generation){
  if(source==='off'||generation!==sourceGeneration||!credential)return;
  const canvas=$('captureCanvas'),ctx=canvas.getContext('2d');
  try{
    if(source==='demo')drawDemo(ctx);else ctx.drawImage($('captureVideo'),0,0,960,540);
    const jpeg=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.65));
    if(source==='off'||generation!==sourceGeneration)return;
    const response=await fetch(base()+'/frame',{method:'POST',headers:{...auth(),'Content-Type':'image/jpeg'},body:jpeg});
    if(!response.ok)throw new Error('Broadcast stopped by the server.');
    if(source==='demo'&&Date.now()-lastSimulation>1600){lastSimulation=Date.now();await control('simulate',{people});}
  }catch(error){stopCapture();toast(error.message,true);return;}
  setTimeout(()=>captureLoop(generation),240);
}
function reset(){
  stopCapture();if(streamAbort)streamAbort.abort();credential=null;state=null;sessionStorage.removeItem('surveillance-session');
  roundSignature=scenarioSignature=historySignature=logSignature=settingsSignature='';lastFrame=-1;
  if(feedURL)URL.revokeObjectURL(feedURL);feedURL=null;$('feed').removeAttribute('src');$('feed').hidden=true;
  $('workspace').hidden=true;$('landing').hidden=false;$('connection').textContent='LOCAL EXPERIENCE';$('connection').className='badge';
}
$('createForm').onsubmit=guard(async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const data=Object.fromEntries(new FormData(event.target));await enter(await api('/api/rooms',data));await startSource('camera');}finally{button.disabled=false;}});
$('joinForm').onsubmit=guard(async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const data=Object.fromEntries(new FormData(event.target));await enter(await api(`/api/rooms/${data.code.trim().toUpperCase()}/join`,{name:data.name}));}finally{button.disabled=false;}});
$('copyLink').onclick=guard(async()=>{
  const url=new URL(location.origin);url.searchParams.set('room',state.code);
  if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(url.href);toast('Join link copied. On other devices, use your server’s network address.');}
  else window.prompt('Copy this participant link:',url.href);
});
$('leave').onclick=guard(async()=>{if(credential.role==='manager'&&source!=='off'){await control('source',{source:'off'});}reset();});
$('demo').onclick=guard(()=>startSource('demo'));
$('camera').onclick=guard(()=>startSource('camera'));
$('stop').onclick=guard(async()=>{stopCapture();await control('source',{source:'off'});});
$('demoPeople').oninput=event=>{people=Number(event.target.value);$('demoCount').textContent=people;};
$('settingsForm').onsubmit=guard(async event=>{event.preventDefault();const form=event.target;await control('settings',{automatic:form.elements.automatic.checked,visionTriggers:form.elements.visionTriggers.checked,interval:Number(form.elements.interval.value),duration:Number(form.elements.duration.value)});toast('Prompt settings applied.');});
$('toggleCustom').onclick=()=>{$('customForm').hidden=!$('customForm').hidden;};
$('customForm').onsubmit=guard(async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));data.options=data.options.split('\n').map(x=>x.trim()).filter(Boolean);await control('custom',data);event.target.reset();event.target.hidden=true;toast('Scenario added to this room.');});
$('endSession').onclick=guard(async()=>{if(!confirm('End this session for everyone? Active voting will be revealed and broadcasting will stop.'))return;await control('end');stopCapture();});
$('export').onclick=guard(async()=>{const response=await fetch(base()+'/export',{headers:auth()});if(!response.ok)throw new Error('Export failed.');const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`surveillance-${state.code}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
window.addEventListener('pagehide',()=>{if(captureStream)captureStream.getTracks().forEach(t=>t.stop());});
setInterval(updateTimer,200);
(async()=>{
  try{health=await api('/api/health');}catch{toast('Cannot reach the server. Check that it is running.',true);}
  $('visionHint').textContent=health.vision?'Vision enabled: offline OpenCV HOG person detection. Best with well-lit, upright, full-body people. Scores are not probabilities.':'Vision disabled. Demo detections are simulated. Restart with --vision to enable the real offline person detector.';
  const room=new URLSearchParams(location.search).get('room');if(room)$('code').value=room.toUpperCase().slice(0,6);
  try{const saved=JSON.parse(sessionStorage.getItem('surveillance-session'));if(saved?.token)await enter(saved);}catch{reset();toast('The saved room is unavailable. Join or create a session.',true);}
  pollFrame();
})();
