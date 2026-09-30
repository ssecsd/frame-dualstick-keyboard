import importlib.util
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frame_profile', ROOT / 'profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'basicui_gamepad.vdf'
        self.original = (ROOT / 'basicui_gamepad.original.vdf').read_bytes()
        self.patched = (ROOT / 'basicui_gamepad.patched.vdf').read_bytes()
        self.target.write_bytes(self.original)
        self.target.chmod(0o640)

    def test_apply_repeat_and_exact_restore(self):
        self.assertEqual(profile.update_profile(self.target, 'status'), 'original')
        profile.update_profile(self.target, 'apply')
        self.assertEqual(self.target.read_bytes(), self.patched)
        self.assertEqual(profile.update_profile(self.target, 'status'), 'patched')
        self.assertEqual(profile.update_profile(self.target, 'apply'), 'Already patched')
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        profile.update_profile(self.target, 'restore')
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(profile.update_profile(self.target, 'restore'), 'Already original')

    def test_unknown_version_is_never_overwritten(self):
        newer = self.original + b'\n// changed by Steam\n'
        self.target.write_bytes(newer)
        self.assertEqual(profile.update_profile(self.target, 'status'), 'different-version')
        for action in ['apply', 'restore']:
            with self.assertRaisesRegex(ValueError, 'Steam profile has changed'):
                profile.update_profile(self.target, action)
            self.assertEqual(self.target.read_bytes(), newer)

    def test_corrupt_bundle_is_never_installed(self):
        bundle = Path(self.temp.name) / 'bundle'
        bundle.mkdir()
        shutil.copyfile(ROOT / 'checksums.json', bundle / 'checksums.json')
        (bundle / 'basicui_gamepad.patched.vdf').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Source checksum mismatch'):
            profile.update_profile(self.target, 'apply', bundle)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_failed_replace_preserves_original_and_cleans_temporary_file(self):
        with patch.object(profile.os, 'replace', side_effect=OSError('replacement failed')):
            with self.assertRaisesRegex(OSError, 'replacement failed'):
                profile.update_profile(self.target, 'apply')
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(list(self.target.parent.glob('.frame-dualstick-*')), [])


# Preserve repeated VDF keys such as group and preset when comparing profiles.
def parse_vdf(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]', text)

    def read(index, nested=False):
        pairs = []
        while index < len(tokens):
            if tokens[index] == '}':
                if not nested:
                    raise ValueError('Unexpected closing brace')
                return pairs, index + 1
            key = tokens[index]
            if not key.startswith('"'):
                raise ValueError('Expected a key')
            index += 1
            if tokens[index] == '{':
                value, index = read(index + 1, True)
            else:
                if not tokens[index].startswith('"'):
                    raise ValueError('Expected a value')
                value = tokens[index][1:-1]
                index += 1
            pairs.append((key[1:-1], value))
        if nested:
            raise ValueError('Unclosed object')
        return pairs, index

    return read(0)[0]


def get(pairs, key):
    return next(value for name, value in pairs if name == key)


class MappingTests(unittest.TestCase):
    def test_only_keyboard_controls_change(self):
        def load(filename):
            return get(parse_vdf((ROOT / filename).read_text()), 'controller_mappings')

        original = load('basicui_gamepad.original.vdf')
        changed = load('basicui_gamepad.patched.vdf')
        self.assertEqual(len(original), len(changed))
        expected = {('group', '41'), ('group', '43'), ('preset', '3')}
        seen = set()
        for (key, old), (newkey, new) in zip(original, changed):
            self.assertEqual(key, newkey)
            if old == new or key == 'title':
                continue
            identity = (key, get(old, 'id'))
            self.assertIn(identity, expected)
            self.assertEqual(get(new, 'id'), identity[1])
            seen.add(identity)
        self.assertEqual(seen, expected)

        for identity, analog, touch in [
            ('41', 'RIGHTPAD_ANALOG', 'RightTrackpad'),
            ('43', 'LEFTPAD_ANALOG', 'LeftTrackpad'),
        ]:
            group = next(value for key, value in changed if key == 'group' and get(value, 'id') == identity)
            self.assertEqual(get(get(group, 'gameactions'), 'Keyboard'), analog)
            touch_input = get(get(group, 'inputs'), 'touch')
            bindings = get(get(get(touch_input, 'activators'), 'Full_Press'), 'bindings')
            self.assertEqual(get(bindings, 'binding'), 'game_action Keyboard ' + touch)

        keyboard = next(value for key, value in changed if key == 'preset' and get(value, 'id') == '3')
        bindings = get(keyboard, 'group_source_bindings')
        self.assertEqual(get(bindings, '41'), 'right_joystick active')
        self.assertEqual(get(bindings, '43'), 'joystick active')
        self.assertEqual(get(bindings, '29'), 'joystick inactive')

    def test_bundle_checksums_match(self):
        checks = json.loads((ROOT / 'checksums.json').read_text())
        for kind, expected in checks.items():
            self.assertEqual(profile.digest((ROOT / f'basicui_gamepad.{kind}.vdf').read_bytes()), expected)


if __name__ == '__main__':
    unittest.main()
