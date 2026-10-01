#!/usr/bin/env python3
"""Install or restore the Steam keyboard mapping and cursor fix with version checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

import ui_patch

BUNDLE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare_profile(target, mode, bundle=BUNDLE):
    checks = json.loads((bundle / 'checksums.json').read_text())
    current = target.read_bytes()
    state = next((key for key, value in checks.items() if value == digest(current)), 'different-version')
    if mode == 'status':
        return state, current, current

    wanted = 'patched' if mode == 'apply' else 'original'
    if state == wanted:
        return state, current, current
    if state == 'different-version':
        raise ValueError(
            'Steam profile has changed. Refusing to overwrite it; '
            'rebase this patch against the installed version.'
        )

    source = bundle / f'basicui_gamepad.{wanted}.vdf'
    data = source.read_bytes()
    if digest(data) != checks[wanted]:
        raise ValueError('Source checksum mismatch')
    return state, current, data


def atomic_replace(target, current, data):
    # Keep the temporary file on the same filesystem for an atomic replacement.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix='.frame-dualstick-', delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
        if target.read_bytes() != current:
            raise ValueError('Steam file changed during installation; please retry.')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def update_profile(target, mode, bundle=BUNDLE):
    state, current, data = prepare_profile(target, mode, bundle)
    if mode == 'status':
        return state
    wanted = 'patched' if mode == 'apply' else 'original'
    if current == data:
        return f'Already {wanted}'
    atomic_replace(target, current, data)
    return f'Installed {wanted} native keyboard profile. Restart Steam to activate it.'


def update_installation(steam_dir, mode, bundle=BUNDLE):
    target = steam_dir / 'controller_base/basicui_gamepad.vdf'
    state, current, data = prepare_profile(target, mode, bundle)
    plans = [('Controller profile', target, state, current, data)]
    # Validate both files before changing either one.
    plans.append(('Keyboard UI', *ui_patch.prepare(steam_dir, mode, bundle)))
    if mode == 'status':
        return '\n'.join(f'{label}: {state}' for label, _, state, _, _ in plans)

    applied = []
    try:
        for label, target, state, current, data in plans:
            if current != data:
                atomic_replace(target, current, data)
                applied.append((label, target, current, data))
    except (OSError, ValueError) as error:
        failures = []
        for label, target, current, data in reversed(applied):
            try:
                atomic_replace(target, data, current)
            except (OSError, ValueError) as rollback_error:
                failures.append(f'{label}: {rollback_error}')
        if failures:
            raise OSError('Installation failed and rollback was incomplete: ' +
                          '; '.join(failures)) from error
        raise

    wanted = 'patched' if mode == 'apply' else 'original'
    prefix = 'Installed' if applied else 'Already'
    return f'{prefix} {wanted} controller profile and keyboard UI. Restart Steam to activate changes.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['apply', 'restore', 'status'], default='status', nargs='?')
    parser.add_argument(
        '--steam-dir', type=Path,
        default=Path.home() / '.local/share/Steam',
        help='Steam installation directory (default: ~/.local/share/Steam)',
    )
    args = parser.parse_args()
    try:
        print(update_installation(args.steam_dir.resolve(), args.mode))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
