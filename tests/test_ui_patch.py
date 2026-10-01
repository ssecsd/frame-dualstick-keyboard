import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import profile
import ui_patch


ROOT = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        for name in ['checksums.json', 'basicui_gamepad.original.vdf',
                     'basicui_gamepad.patched.vdf', 'keyboard-center.mjs']:
            shutil.copyfile(ROOT / name, self.bundle / name)
        self.profile = self.root / 'controller_base/basicui_gamepad.vdf'
        self.profile.parent.mkdir()
        self.original_profile = (ROOT / 'basicui_gamepad.original.vdf').read_bytes()
        self.profile.write_bytes(self.original_profile)
        self.ui = self.root / 'steamui/test.js'
        self.ui.parent.mkdir()
        reserve = b'var unusedBuildMarker="' + b'x' * 2400 + b'";'
        self.reserves = [{'offset': len(b'prefix;'), 'text': reserve.decode()}]
        self.original_ui = b'prefix;' + reserve + ui_patch.MOUNT + b';middle;' + ui_patch.UNMOUNT + b';suffix'
        self.ui.write_bytes(self.original_ui)
        unpadded = ui_patch.transform(self.original_ui, 'apply', self.bundle, self.reserves)
        self.padding = len(self.original_ui) - len(unpadded)
        self.assertGreaterEqual(self.padding, 0)
        changed = ui_patch.transform(self.original_ui, 'apply', self.bundle, self.reserves, self.padding)
        self.legacy_ui = ui_patch.transform_hooks(self.original_ui, 'apply', self.bundle)
        self.checks = {'file': 'steamui/test.js', 'original': ui_patch.digest(self.original_ui),
                       'patched': ui_patch.digest(changed), 'previous_patched': ui_patch.digest(self.legacy_ui),
                       'original_size': len(self.original_ui), 'reserves': self.reserves, 'padding': self.padding}
        (self.bundle / 'ui-checksums.json').write_text(json.dumps(self.checks))

    def update(self, action):
        return profile.update_installation(self.root, action, self.bundle)

    def test_new_install_repeat_and_exact_restore_of_both_files(self):
        self.update('apply')
        self.assertEqual(ui_patch.digest(self.ui.read_bytes()), self.checks['patched'])
        self.assertEqual(self.ui.stat().st_size, len(self.original_ui))
        self.assertEqual(self.update('status'), 'Controller profile: patched\nKeyboard UI: patched')
        self.assertTrue(self.update('apply').startswith('Already'))
        self.update('restore')
        self.assertEqual(self.profile.read_bytes(), self.original_profile)
        self.assertEqual(self.ui.read_bytes(), self.original_ui)

    def test_upgrade_from_profile_only_installation(self):
        patched = (ROOT / 'basicui_gamepad.patched.vdf').read_bytes()
        previous = patched.split(b'// Steam startup size padding: ', 1)[0]
        self.profile.write_bytes(previous)
        self.update('apply')
        self.assertEqual(self.profile.read_bytes(), patched)
        self.assertEqual(ui_patch.digest(self.ui.read_bytes()), self.checks['patched'])

    def test_previous_ui_patch_can_upgrade_or_restore(self):
        for action, expected in [('apply', self.checks['patched']), ('restore', self.checks['original'])]:
            self.ui.write_bytes(self.legacy_ui)
            self.assertIn('Keyboard UI: patched-v1', self.update('status'))
            self.update(action)
            self.assertEqual(ui_patch.digest(self.ui.read_bytes()), expected)
            self.assertEqual(self.ui.stat().st_size, len(self.original_ui))

    def test_unsupported_ui_is_rejected_before_any_file_changes(self):
        newer = self.original_ui + b';new Steam release'
        self.ui.write_bytes(newer)
        with self.assertRaisesRegex(ValueError, 'Steam keyboard UI has changed'):
            self.update('apply')
        self.assertEqual(self.ui.read_bytes(), newer)
        self.assertEqual(self.profile.read_bytes(), self.original_profile)

    def test_modified_helper_is_rejected_before_any_file_changes(self):
        helper = self.bundle / 'keyboard-center.mjs'
        helper.write_bytes(helper.read_bytes() + b'\n// changed\n')
        with self.assertRaisesRegex(ValueError, 'patch checksum mismatch'):
            self.update('apply')
        self.assertEqual(self.ui.read_bytes(), self.original_ui)
        self.assertEqual(self.profile.read_bytes(), self.original_profile)

    def test_second_file_failure_rolls_back_first_file(self):
        real_replace = profile.atomic_replace

        def fail_ui(target, current, data):
            if target == self.ui:
                raise OSError('simulated UI write failure')
            real_replace(target, current, data)

        with patch.object(profile, 'atomic_replace', side_effect=fail_ui):
            with self.assertRaisesRegex(OSError, 'simulated UI write failure'):
                self.update('apply')
        self.assertEqual(self.profile.read_bytes(), self.original_profile)
        self.assertEqual(self.ui.read_bytes(), self.original_ui)

    def test_reverse_patch_preserves_surrounding_bytes(self):
        changed = ui_patch.transform(self.original_ui, 'apply', self.bundle, self.reserves, self.padding)
        self.assertEqual(ui_patch.transform(changed, 'restore', self.bundle, self.reserves, self.padding), self.original_ui)
        with self.assertRaisesRegex(ValueError, 'hooks do not match'):
            ui_patch.transform(self.original_ui + ui_patch.MOUNT, 'apply', self.bundle)


if __name__ == '__main__':
    unittest.main()
