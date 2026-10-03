# pUSA Run

A three-lane endless runner you can play with your body or a keyboard. Move left or right to change lanes, jump over obstacles, and keep Pipin ahead of the rat.

## Requirements

- Windows 10 or 11 (64-bit)
- Python 3.11, 64-bit (check with `py -3.11 --version`)
- A webcam if you want to use body controls; keyboard play works without one

The Python packages are listed in [requirements.txt](requirements.txt). The setup command below installs them for you.

## Install and play

Open PowerShell in the project folder, then run:

```powershell
.\scripts\setup_windows.ps1
.\.venv\Scripts\python.exe run_game.py
```

If PowerShell blocks the setup script, run this first and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

To install the requirements manually instead:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_game.py
```

Use `run_game.py`, not `main.py`. After the first setup, you only need the run command.

## Controls

| Action                                     | Camera                               | Keyboard                     |
| ---                                        | ---                                  | ---                          |
| Left lane                                  | Move into the left camera zone       | A or Left Arrow              |
| Middle lane                                | Move into the middle camera zone     | Move back with A/D or arrows |
| Right lane                                 | Move into the right camera zone      | D or Right Arrow             |
| Jump                                       | Rise above your calibrated jump line | Space, W, or Up Arrow        |
| Pause or go back                           | —                                    | Esc                          |
| Show/hide camera window                    | —                                    | F2                           |
| Fullscreen                                 | —                                    | F11                          |

For camera play, stand about 1–1.5 metres away with your head, shoulders, torso, and hips visible. Stay still until calibration finishes. If the camera cannot see you, Pipin keeps running; you can still use the keyboard. Choose **Keyboard Only** on the calibration screen to play without a camera.

Camera frames are processed in memory and are not saved.

## Optional

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

To make a Windows build, run `.\scripts\build_windows.ps1`. See [assets/README.md](assets/README.md) for asset sizes and formats.
