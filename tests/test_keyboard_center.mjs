import assert from 'node:assert/strict';
import test from 'node:test';
import {startFrameKeyboardKeepalive} from '../keyboard-center.mjs';

function setup(controllers = [[0, {controllerType:21, activeButtons:{19:true,21:true}}]]) {
  let tick;
  const analogListeners = new Set();
  const releaseListeners = new Set();
  const register = (listeners, callback) => {
    listeners.add(callback);
    return {Unregister: () => listeners.delete(callback)};
  };
  const events = [];
  const input = {
    m_rgControllers:new Map(controllers),
    RegisterForAnalog: callback => register(analogListeners, callback),
    RegisterForGamepadButtonUp: callback => register(releaseListeners, callback),
    OnAnalogPad(pad,x,y,index) {
      events.push({pad,x,y,index});
      for (const callback of analogListeners) callback(pad,index,x,y);
    },
  };
  const clock = {
    setInterval(callback, delay) {assert.equal(delay,40);tick=callback;return 1;},
    clearInterval(id) {assert.equal(id,1);tick=undefined;},
  };
  const stop = startFrameKeyboardKeepalive(input,clock);
  return {input,events,stop,analogListeners,releaseListeners,
    tick: () => tick?.(),
    move: (pad,x,y,index=0) => input.OnAnalogPad(pad,x,y,index),
    release(pad,index=0) {
      input.m_rgControllers.get(index).activeButtons[pad]=false;
      for (const callback of releaseListeners) callback(pad,1,index);
    },
  };
}

test('keeps both neutral cursors alive without any initial analog packet', () => {
  const s=setup();
  for(let i=0;i<10;i++) s.tick();
  assert.equal(s.events.length,20);
  assert.ok(s.events.every(e=>e.x===0&&e.y===0&&e.index===0));
  assert.deepEqual([...new Set(s.events.map(e=>e.pad))],[19,21]);
});

test('retains the last coordinates and accepts a return to exactly zero', () => {
  const s=setup();
  s.move(19,-0.4,0.7);s.tick();
  assert.deepEqual(s.events.at(-2),{pad:19,x:-0.4,y:0.7,index:0});
  s.move(19,0,0);s.tick();s.tick();
  assert.deepEqual(s.events.at(-2),{pad:19,x:0,y:0,index:0});
});

test('stops on release and recenters after a quick release and retouch', () => {
  const s=setup();
  s.move(19,0.8,0.5);s.release(19);s.release(21);
  s.events.length=0;s.tick();
  assert.equal(s.events.length,0);
  s.input.m_rgControllers.get(0).activeButtons[19]=true;s.tick();
  assert.deepEqual(s.events,[{pad:19,x:0,y:0,index:0}]);
});

test('ignores other controller types and clears disconnected coordinates', () => {
  const s=setup([[0,{controllerType:21,activeButtons:{19:true}}],
    [1,{controllerType:3,activeButtons:{19:true,21:true}}]]);
  s.move(19,0.8,0.5);s.input.m_rgControllers.delete(0);
  s.events.length=0;s.tick();assert.equal(s.events.length,0);
  s.input.m_rgControllers.set(0,{controllerType:21,activeButtons:{19:true}});
  s.tick();assert.deepEqual(s.events,[{pad:19,x:0,y:0,index:0}]);
});

test('cleanup removes timers and subscriptions and is idempotent', () => {
  const s=setup();s.stop();s.stop();s.tick();
  assert.equal(s.events.length,0);
  assert.equal(s.analogListeners.size,0);
  assert.equal(s.releaseListeners.size,0);
});
