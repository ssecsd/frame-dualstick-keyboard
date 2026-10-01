// The native keyboard hides a cursor after 100 ms without analog messages.
// Frame stops sending those messages at (0, 0), even with a thumb on the stick.
export function startFrameKeyboardKeepalive(input, clock = globalThis) {
  const FRAME_CONTROLLER = 21;
  const PADS = [19, 21]; // Steam UI's LPAD_TOUCH and RPAD_TOUCH.
  const positions = new Map();
  let replaying = false;
  let stopped = false;
  const keyFor = (index, pad) => `${index}:${pad}`;
  const analog = input.RegisterForAnalog((pad, index, x, y) => {
    if (!replaying && PADS.includes(pad) &&
        input.m_rgControllers.get(index)?.controllerType === FRAME_CONTROLLER) {
      positions.set(keyFor(index, pad), {index, pad, x, y});
    }
  });
  const release = input.RegisterForGamepadButtonUp((pad, source, index) => {
    positions.delete(keyFor(index, pad));
  });

  const tick = () => {
    for (const [key, position] of positions) {
      const controller = input.m_rgControllers.get(position.index);
      if (controller?.controllerType !== FRAME_CONTROLLER ||
          !controller.activeButtons[position.pad]) positions.delete(key);
    }
    for (const [index, controller] of input.m_rgControllers) {
      if (controller.controllerType !== FRAME_CONTROLLER) continue;
      for (const pad of PADS) {
        if (!controller.activeButtons[pad]) continue;
        const {x, y} = positions.get(keyFor(index, pad)) ?? {x: 0, y: 0};
        // Reuse native cursor handling. This never generates button presses.
        replaying = true;
        try { input.OnAnalogPad(pad, x, y, index); }
        finally { replaying = false; }
      }
    }
  };
  const timer = clock.setInterval(tick, 40);
  return () => {
    if (stopped) return;
    stopped = true;
    clock.clearInterval(timer);
    analog.Unregister();
    release.Unregister();
    positions.clear();
  };
}
