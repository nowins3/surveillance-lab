// Camera lifecycle checks without a physical webcam or browser dependencies.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const app = readFileSync(require('node:path').join(__dirname, '../public/app.js'), 'utf8');

function cameraHarness(options = {}) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {play: async () => {
      if (options.playError) throw options.playError;
    }});
    return elements.get(id);
  };
  const track = {stopped: false, stop() {this.stopped = true;}};
  const stream = {getTracks: () => [track], getVideoTracks: () => [track]};
  const calls = [], loops = [], requests = [];
  const context = vm.createContext({
    $: element, window: {isSecureContext: options.secure !== false},
    navigator: {mediaDevices: {getUserMedia: async constraints => {
      requests.push(constraints);
      if (options.getStream) return options.getStream();
      return stream;
    }}},
    credential: {role: options.role || 'manager'}, state: {ended: false},
    source: 'off', sourceGeneration: 0, captureStream: null, lastSimulation: 0,
    control: async (...args) => {calls.push(args); if (options.controlError) throw options.controlError;},
    toast: () => {}, captureLoop: generation => loops.push(generation)
  });
  vm.runInContext(app.slice(app.indexOf('function stopCapture(){'), app.indexOf('async function captureLoop(')), context);
  return {context, element, track, stream, calls, loops, requests};
}

test('manager broadcasts their default device camera with no audio', async () => {
  const h = cameraHarness();
  await h.context.startSource('camera');
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].audio, false);
  assert.equal(h.requests[0].video.facingMode, undefined);
  assert.equal(h.context.source, 'camera');
  assert.equal(h.element('captureVideo').srcObject, h.stream);
  assert.equal(h.calls[0][1].source, 'camera');
  assert.equal(h.loops.length, 1);
  h.context.stopCapture();
  assert.equal(h.track.stopped, true);
  assert.equal(h.element('captureVideo').srcObject, null);
});

test('participants never request camera access', async () => {
  const h = cameraHarness({role: 'participant'});
  await h.context.startSource('camera');
  assert.equal(h.requests.length, 0);
  assert.equal(h.calls.length, 0);
});

test('permission denial leaves a useful retry message and no broadcast', async () => {
  const h = cameraHarness({getStream: async () => {throw Object.assign(new Error(), {name:'NotAllowedError'});}});
  await assert.rejects(h.context.startSource('camera'), /permission was denied/);
  assert.match(h.element('cameraHint').textContent, /click Share camera/);
  assert.equal(h.context.source, 'off');
  assert.equal(h.calls.length, 0);
});

test('insecure remote origins explain HTTPS without requesting a camera', async () => {
  const h = cameraHarness({secure: false});
  await assert.rejects(h.context.startSource('camera'), /requires HTTPS/);
  assert.equal(h.requests.length, 0);
});

test('playback or server failures release the camera', async () => {
  for (const options of [{playError: new Error('Playback failed')}, {controlError: new Error('Server unavailable')}]) {
    const h = cameraHarness(options);
    await assert.rejects(h.context.startSource('camera'));
    assert.equal(h.track.stopped, true);
    assert.equal(h.context.source, 'off');
    assert.equal(h.loops.length, 0);
  }
});

test('leaving while permission is pending releases a late stream', async () => {
  let resolve;
  const pending = new Promise(done => {resolve = done;});
  const h = cameraHarness({getStream: () => pending});
  const start = h.context.startSource('camera');
  h.context.stopCapture();
  resolve(h.stream);
  await start;
  assert.equal(h.track.stopped, true);
  assert.equal(h.calls.length, 0);
  assert.equal(h.loops.length, 0);
});

test('creating a room enters the manager session before starting its camera', async () => {
  const calls = [], form = {}, button = {disabled:false};
  const context = vm.createContext({
    $: () => form, guard: fn => fn, enableAlarm: async () => {}, FormData: class { *[Symbol.iterator]() {yield ['title', 'Room'];} },
    api: async path => {calls.push(path); return {role:'manager'};},
    enter: async data => calls.push(data.role), startSource: async source => calls.push(source)
  });
  vm.runInContext(app.slice(app.indexOf("$('createForm').onsubmit="), app.indexOf("$('joinForm').onsubmit=")), context);
  await form.onsubmit({preventDefault() {}, submitter:button, target:{}});
  assert.deepEqual(calls, ['/api/rooms', 'manager', 'camera']);
  assert.equal(button.disabled, false);
});
