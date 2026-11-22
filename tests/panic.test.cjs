const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const app = readFileSync(require('node:path').join(__dirname, '../public/app.js'), 'utf8');

function harness() {
  const elements = new Map(), classes = new Set(), timers = new Set();
  let pulses = 0, volume = null;
  const element = id => {
    if (!elements.has(id)) elements.set(id, {focus() {}, scrollIntoView() {}});
    return elements.get(id);
  };
  class AudioContext {
    constructor() {this.currentTime = 0; this.state = 'suspended';}
    async resume() {this.state = 'running';}
    async decodeAudioData() {return {recording:true};}
    createGain() {return {connect() {}, disconnect() {}, gain: {
      cancelScheduledValues() {}, setValueAtTime(v) {volume = v;}, linearRampToValueAtTime(v) {volume = v;}, exponentialRampToValueAtTime(v) {volume = v;}
    }};}
    createBufferSource() {const source={connect() {}, disconnect() {}, start() {pulses++;timers.add(source);volume=1;}, stop() {timers.delete(source);volume=0;}};return source;}
  }
  const context = vm.createContext({
    $: element, window: {AudioContext}, connected: true,
    fetch: async url => {assert.equal(url, '/assets/mixkit-classic-alarm-995.wav');return {ok:true,arrayBuffer:async()=>new ArrayBuffer(8)};},
    toast: message => {throw new Error(message);},
    state: {panic: true, ended: false, role: 'manager'},
    document: {hidden: false, body: {classList: {
      contains: name => classes.has(name), toggle: (name, active) => active ? classes.add(name) : classes.delete(name)
    }}},
    setInterval: fn => {timers.add(fn);return fn;}, clearInterval: id => timers.delete(id)
  });
  vm.runInContext(app.slice(app.indexOf('let alarmContext'), app.indexOf('const base =')), context);
  return {context, element, classes, timers, pulses: () => pulses, volume: () => volume};
}

test('alarm needs browser activation, then starts once and stops on shared clear', async () => {
  const h = harness();
  vm.runInContext('renderPanic()', h.context);
  assert.equal(h.element('panicSound').textContent, 'Enable alarm sound');
  assert.equal(h.pulses(), 0);
  await vm.runInContext('enableAlarm()', h.context);
  vm.runInContext('renderPanic();renderPanic()', h.context);
  assert.equal(h.pulses(), 1);
  assert.equal(h.timers.size, 1);
  vm.runInContext('state.panic=false;renderPanic()', h.context);
  assert.equal(h.timers.size, 0);
  assert.equal(h.volume(), 0);
  assert.equal(h.classes.has('panic-active'), false);
});

test('local mute, hidden tabs, and session end silence the siren', async () => {
  const h = harness();
  await vm.runInContext('enableAlarm()', h.context);
  vm.runInContext('alarmMuted=true;renderPanic()', h.context);
  assert.equal(h.volume(), 0);
  assert.equal(h.timers.size, 0);
  assert.equal(h.element('panicAlert').hidden, false);
  vm.runInContext('alarmMuted=false;document.hidden=true;renderPanic()', h.context);
  assert.equal(h.timers.size, 0);
  vm.runInContext('document.hidden=false;renderPanic()', h.context);
  assert.equal(h.timers.size, 1);
  vm.runInContext('state.ended=true;renderPanic()', h.context);
  assert.equal(h.timers.size, 0);
  assert.equal(h.volume(), 0);
  assert.equal(h.element('panicAlert').hidden, true);
});
