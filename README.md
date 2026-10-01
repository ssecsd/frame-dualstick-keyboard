# Steam Frame Dual Stick Keyboard

Control Steam's built-in on-screen keyboard with both Steam Frame controller
sticks. The left stick selects keys in the left area, the right stick selects
keys in the right area, and each trigger presses its selected key.

Controller navigation and text entry were confirmed working on a Steam Frame
on September 30, 2026. This enables Steam's existing keyboard cursors; Steam
continues to handle panel focus, keyboard layouts, and text input.
The keyboard also receives a small UI fix so its cursors stay active at the
center of each stick while your thumbs are touching them. This behavior was
confirmed on the Frame on October 1, 2026.

## Installation

### Prepare your Steam Frame

1. Open **Settings** on the Frame and enable **Developer Mode**.
2. Open **Developer settings** and set **User Password** for the `steamos`
   account. Use this password when connecting over SSH.
3. Find the Frame's IP address and make sure your computer can reach it on
   the same network.

Python 3.8+ and access to the user's Steam files are required. Installing from
Git also requires Git. Root access is not required.

### Install over SSH

Connect to your Frame from a terminal on your computer, replacing
`<FRAME_IP>` with its IP address:

```sh
ssh steamos@<FRAME_IP>
```

Enter the **User Password** you configured in Developer settings when prompted.
Then run these commands in the SSH session:

```sh
mkdir -p ~/.local/share
git clone https://github.com/ssecsd/frame-dualstick-keyboard.git ~/.local/share/frame-dualstick-keyboard
python3 ~/.local/share/frame-dualstick-keyboard/profile.py apply
```

Restart Steam or the headset, then open the normal on-screen keyboard.
If this directory already contains a previously installed copy, you do not
need to clone it again: run its `profile.py apply` command.

Alternatively, download the repository using **Code → Download ZIP**, extract
it on the Frame, and run `python3 profile.py apply` from the extracted directory.
Keep the directory: it contains the files needed to restore the original profile.

The installer checks the exact contents of both the base profile and the keyboard
UI before changing either file. If it reports that Steam's profile or keyboard UI
has changed, this patch must be adapted to that version; it will not overwrite
unrecognized files. The tested UI build is `11041156`.

### Update an existing installation

For a Git installation, run on the Frame:

```sh
git -C ~/.local/share/frame-dualstick-keyboard pull --ff-only
python3 ~/.local/share/frame-dualstick-keyboard/profile.py apply
```

For a ZIP installation, download and extract the latest ZIP, then run its
`python3 profile.py apply`. Restart Steam or the headset afterward. The original
profile-only release can be upgraded directly, without uninstalling it first.

## Controls

- Keep your thumbs on the sticks: touching each stick activates its cursor.
- The stick direction sets the cursor position within its keyboard area.
- The left and right triggers press the keys selected by their respective cursors.
- Use the normal pointer to select a panel and text field.

Trigger confirmation depends on Steam's `TrackpadTypingTriggerAsClick` setting.
It was already enabled on the tested device; the installer does not change it.
If the cursors work but the triggers produce Shift/Enter, check this setting.

## Status and rollback

```sh
python3 ~/.local/share/frame-dualstick-keyboard/profile.py status
python3 ~/.local/share/frame-dualstick-keyboard/profile.py restore
```

`status` reports `original`, `patched`, or `different-version` separately for
the controller profile and keyboard UI. `restore` restores both original files.
Restart Steam after restoring the original profile. Repeated installation and
rollback are safe: the installer detects when the requested state is already applied.

For a nonstandard Steam installation directory:

```sh
python3 profile.py apply --steam-dir /path/to/Steam
```

## How it works

The patch modifies `~/.local/share/Steam/controller_base/basicui_gamepad.vdf`.
Within the `Keyboard` action set:

- Existing analog groups 41 and 43 are enabled, using `RIGHTPAD_ANALOG` and
  `LEFTPAD_ANALOG`.
- Stick touch is mapped to `RightTrackpad` and `LeftTrackpad` so the keyboard
  accepts coordinates for both cursors.
- Group 29, which moved a single selection, is disabled only in this action set.

Other action sets are preserved. The change also affects other controllers that
use this base profile on the same device.

The installer also patches the keyboard's mount and unmount hooks in
`steamui/chunk~2dcc5aaf7.js` to run `keyboard-center.mjs` while the keyboard is
mounted. Steam stops sending analog coordinates when a stick returns to `(0, 0)`;
its keyboard normally hides a cursor after 100 ms without coordinates. The helper
refreshes the last position every 40 ms while the corresponding stick is touched,
including a neutral position when no initial analog message arrives. It stops
refreshing after release and cleans up when the keyboard unmounts. This UI fix
applies only to Steam Frame controllers and generates no button presses.

A Steam update may replace either file and remove the corresponding patch.

The tested Steam version did not apply a separate user profile for the system
interface (application 769), so the patch changes the base file it actually loads.
Files under `/opt/steamvr` are not modified.

`basicui_gamepad.original.vdf` is Valve's original profile.
`basicui_gamepad.patched.vdf` is the same profile with the changes described above.
Exact profile checksums are stored in `checksums.json`. UI checksums are stored
in `ui-checksums.json`; the installer applies a small reversible edit to the local
Steam file rather than distributing the complete UI bundle.
Git preserves the VDF file bytes without converting line endings.

## Reloading the profile without restarting Steam

The optional `reload.mjs` tool reloads only the controller profile, not the
keyboard UI fix. Restart Steam to load changes to the UI fix. The tool uses an
already enabled Steam debugging interface.
It is not needed for normal installation. It requires Node.js 22+ on your computer.

If Steam's debugging interface is listening on `127.0.0.1:8080` on the Frame,
create an SSH tunnel in a separate terminal:

```sh
ssh -N -L 18080:127.0.0.1:8080 steamos@<FRAME_IP>
```

Wake the controllers and open the keyboard, then run these commands on your computer:

```sh
node reload.mjs status http://127.0.0.1:18080
node reload.mjs reload http://127.0.0.1:18080
```

The tool does not enable debugging. It requests a reload of the default profile;
if a separate user profile is selected, it refuses to clear that selection.

## Validation

```sh
python3 -m unittest discover -s tests -v
node --test tests/test_keyboard_center.mjs
node --check reload.mjs
```

Tests cover installation, repeated application, exact rollback, permission
preservation, rejection of incompatible files or corrupted packages, rollback
after a partial installation failure, and preservation of other action sets.
JavaScript tests cover neutral cursor updates, return to zero, release and
retouch, controller filtering, disconnects, and cleanup. Physical input was verified by
the user on a Frame; automated tests operate on temporary copies of the files.
