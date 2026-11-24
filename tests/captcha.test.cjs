const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const app = readFileSync('public/app.js', 'utf8');

function harness() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {innerHTML:'', textContent:'', isConnected:true,
      focus(){}, scrollIntoView(){}});
    return elements.get(id);
  };
  const tiles = Array.from({length:9}, (_, i) => ({dataset:{tile:String(i)},
    classList:{toggle(){}}, setAttribute(){}}));
  const calls=[];
  const context=vm.createContext({$:element, captchaDraft:{id:null,tiles:[]},
    escapeHTML: value => String(value), connected:true,
    state:{participants:2,ended:false},
    document:{querySelectorAll:()=>tiles},
    updateTimer(){}, guard:fn=>fn, control(){}, serverNow:()=>0,
    base:()=>'/api/rooms/TEST',
    api:async(path,data)=>{calls.push({path,data});return {};}, render(){}});
  vm.runInContext(app.slice(app.indexOf('function renderCaptcha('), app.indexOf('function renderRound(')),context);
  const round={id:'captcha-1',status:'open',deadline:100,myVote:null,responses:0,
    options:Array.from({length:9},(_,i)=>`Tile ${i+1}`)};
  return {context,element,tiles,calls,round};
}

test('CAPTCHA keeps unsaved choices across updates and submits all labels together', async()=>{
  const h=harness();
  h.context.renderCaptcha(h.round,false,true);
  assert.equal((h.element('roundContent').innerHTML.match(/data-tile=/g)||[]).length,9);
  h.tiles[4].onclick(); h.tiles[7].onclick(); h.tiles[7].onclick();
  h.context.renderCaptcha(h.round,false,true);
  assert.deepEqual(Array.from(h.context.captchaDraft.tiles),[4]);
  await h.element('captchaVerify').onclick();
  assert.equal(h.calls[0].path,'/api/rooms/TEST/vote');
  assert.equal(JSON.stringify(h.calls[0].data),JSON.stringify({roundId:'captcha-1',tiles:[4]}));
  h.round.id='captcha-2';
  h.context.renderCaptcha(h.round,false,true);
  assert.deepEqual(Array.from(h.context.captchaDraft.tiles),[]);
});

test('reveal shows human selection rates and nine labels per submission',()=>{
  const h=harness();
  h.round={...h.round,status:'revealed',responses:2,counts:[0,0,0,1,2,0,1,2,0],reveal:'A classroom simulation.'};
  h.context.renderCaptcha(h.round,false,false);
  const html=h.element('roundContent').innerHTML;
  assert.match(html,/50% selected/);
  assert.match(html,/100% selected/);
  assert.match(html,/<strong>18<\/strong>/);
  assert.match(html,/pipeline stops at labels/);
  assert.doesNotMatch(html,/id="captchaVerify"/);
});

test('reload restores an all-negative submission as saved',()=>{
  const h=harness();h.round.myVote=[];
  h.context.renderCaptcha(h.round,false,true);
  assert.match(h.element('roundContent').innerHTML,/Thank you for for allowing us to use you for free/);
  assert.match(h.element('roundContent').innerHTML,/Update verification/);
});
