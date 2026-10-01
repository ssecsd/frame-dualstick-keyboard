"""Version-checked, reversible patch to Steam's keyboard mount/unmount hooks."""

import hashlib
import json


MOUNT = b'this.m_trackpadInput.EnableAnalogInputMessages(!0),this.StartControllerInputWatchdogTimer()'
UNMOUNT = b'this.m_trackpadInput.EnableAnalogInputMessages(!1),this.ClearControllerInputWatchdogTimer()'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replacements(bundle):
    source = (bundle / 'keyboard-center.mjs').read_bytes()
    signature = b'export function startFrameKeyboardKeepalive('
    if source.count(signature) != 1:
        raise ValueError('Invalid keyboard helper')
    source = source.replace(signature, b'function startFrameKeyboardKeepalive(', 1)
    mounted = b'this.m_frameDualStickCleanup=(' + source + b')(this.m_trackpadInput),' + MOUNT
    unmounted = b'this.m_frameDualStickCleanup?.(),' + UNMOUNT
    return [(MOUNT, mounted), (UNMOUNT, unmounted)]


def transform(data, mode, bundle):
    for original, patched in replacements(bundle):
        before, after = (original, patched) if mode == 'apply' else (patched, original)
        if data.count(before) != 1:
            raise ValueError('Steam keyboard hooks do not match the supported version')
        data = data.replace(before, after, 1)
    return data


def prepare(steam_dir, mode, bundle):
    checks = json.loads((bundle / 'ui-checksums.json').read_text())
    target = steam_dir / checks['file']
    current = target.read_bytes()
    checksum = digest(current)
    state = next((kind for kind in ['original', 'patched']
                  if checks[kind] == checksum), 'different-version')
    if mode == 'status':
        return target, state, current, current
    wanted = 'patched' if mode == 'apply' else 'original'
    if state == wanted:
        return target, state, current, current
    if state == 'different-version':
        raise ValueError('Steam keyboard UI has changed. Refusing to overwrite it; '
                         'adapt this patch to the installed Steam version.')
    changed = transform(current, mode, bundle)
    if digest(changed) != checks[wanted]:
        raise ValueError('Keyboard UI patch checksum mismatch')
    return target, state, current, changed
