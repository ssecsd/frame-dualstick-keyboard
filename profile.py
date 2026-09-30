#!/usr/bin/env python3
"""Install or restore the native Steam keyboard mapping with version checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

BUNDLE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def update_profile(target, mode, bundle=BUNDLE):
    checks = json.loads((bundle / 'checksums.json').read_text())
    current = digest(target.read_bytes())
    state = next((key for key, value in checks.items() if value == current), 'different-version')
    if mode == 'status':
        return state

    wanted = 'patched' if mode == 'apply' else 'original'
    if state == wanted:
        return f'Already {wanted}'
    if state == 'different-version':
        raise ValueError(
            'Steam profile has changed. Refusing to overwrite it; '
            'rebase this patch against the installed version.'
        )

    source = bundle / f'basicui_gamepad.{wanted}.vdf'
    data = source.read_bytes()
    if digest(data) != checks[wanted]:
        raise ValueError('Source checksum mismatch')

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
        if digest(target.read_bytes()) != current:
            raise ValueError('Steam profile changed during installation; please retry.')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return f'Installed {wanted} native keyboard profile. Restart Steam to activate it.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['apply', 'restore', 'status'], default='status', nargs='?')
    parser.add_argument(
        '--steam-dir', type=Path,
        default=Path.home() / '.local/share/Steam',
        help='Steam installation directory (default: ~/.local/share/Steam)',
    )
    args = parser.parse_args()
    target = (args.steam_dir / 'controller_base/basicui_gamepad.vdf').resolve()
    try:
        print(update_profile(target, args.mode))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
