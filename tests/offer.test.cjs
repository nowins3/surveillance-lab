const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {readFileSync}=require('node:fs');
const app=readFileSync(require('node:path').join(__dirname,'../public/app.js'),'utf8');
function harness(){
  let starts=0,stops=0;
  const elements=new Map(),classes=new Set();
  const $=id=>{if(!elements.has(id))elements.set(id,{hidden:true,focus(){},scrollIntoView(){},setAttribute(){}});return elements.get(id);};
  const context=vm.createContext({$,connected:true,alarmContext:{state:'running',sampleRate:8000,destination:{},
    createBuffer(channels,length){return {getChannelData(){return new Float32Array(length);}};},
    createBufferSource(){return {connect(){},disconnect(){},start(){starts++;},stop(){stops++;}};}
  },state:{role:'participant',offer:{id:'offer-1',active:true,myVote:0,myResult:'W Investor'}},
  document:{hidden:false,body:{classList:{toggle(name,active){active?classes.add(name):classes.delete(name);}}}}
  });
  vm.runInContext(app.slice(app.indexOf('let offerPlayed'),app.indexOf('const auth =')),context);
  return {context,$,classes,starts:()=>starts,stops:()=>stops};
}
test('offer chime plays once per offer and participant feedback uses a calm alert',()=>{
  const h=harness();
  vm.runInContext('renderOffer();renderOffer()',h.context);
  assert.equal(h.starts(),1);
  assert.equal(h.$('offerResult').textContent,'W Investor');
  assert.equal(h.$('offerChoices').hidden,false);
  assert.equal(h.classes.has('offer-active'),true);
  vm.runInContext("state.offer.myVote=1;state.offer.myResult='L Investor';renderOffer()",h.context);
  assert.equal(h.$('offerResult').textContent,'L Investor');
  assert.equal(h.starts(),1);
  vm.runInContext('state.panic=true;renderOffer()',h.context);
  assert.equal(h.$('offerAlert').hidden,true);
  assert.equal(h.stops(),1);
  vm.runInContext("state.panic=false;state.offer.id='offer-2';renderOffer()",h.context);
  assert.equal(h.starts(),2);
  vm.runInContext('state.ended=true;renderOffer()',h.context);
  assert.equal(h.$('offerAlert').hidden,true);
  assert.equal(h.stops(),2);
});
test('locked audio waits for activation; presenter sees totals and no voting buttons',()=>{
  const h=harness();
  vm.runInContext("alarmContext.state='suspended';state.role='manager';state.offer.counts=[3,2];state.offer.responses=5;renderOffer()",h.context);
  assert.equal(h.starts(),0);
  assert.equal(h.$('offerChoices').hidden,true);
  assert.match(h.$('offerTally').textContent,/Yes: 3.*No: 2/);
  vm.runInContext("alarmContext.state='running';renderOffer();renderOffer()",h.context);
  assert.equal(h.starts(),1);
});
