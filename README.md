# pUSA Run

pUSA Run is a Windows-first, camera-controlled 2D three-lane endless runner.
The player moves their upper body left or right to change lanes and rises above
a personalized jump line to make Pipin jump. Keyboard controls are always
available.

The current vertical slice integrates the supplied pixel-art menu, characters,
collectibles, and campus track. Obstacles still use a temporary in-game crate
until final obstacle art is available. The full loop includes calibration,
tutorial, increasing difficulty, three hearts, the pursuing rat, Cat Food
shields, Fish healing, scoring, high-score saving, camera selection, pause,
retry, and fullscreen support.

## Requirements

- Windows 10 or 11, 64-bit
- Python 3.11
- A webcam for body controls
- Approximately 1-1.5 metres between the player and camera
- Head, shoulders, torso, and hips visible

Pinned runtime packages:

    opencv-python==4.11.0.86
    mediapipe==0.10.33
    pygame==2.6.1
    numpy==1.26.4

## Setup

From PowerShell:

    .\scripts\setup_windows.ps1
    .\.venv\Scripts\python.exe run_game.py

The official MediaPipe Pose Landmarker Lite model is stored locally under
models so the game does not need internet access while running.

## Controls

| Action | Body control | Keyboard |
| --- | --- | --- |
| Left lane | Move into the left camera zone | A or Left Arrow |
| Middle lane | Return to the middle camera zone | Use A/D or arrows |
| Right lane | Move into the right camera zone | D or Right Arrow |
| Jump | Raise shoulders above the calibrated line | Space, W, or Up Arrow |
| Pause | - | Escape |
| Camera window | - | F2 |
| Fullscreen | - | F11 |

Camera movement maps directly to lanes: left zone selects the left lane, middle
zone selects the middle lane, and right zone selects the right lane. The player
does not need to return to the middle before selecting another lane.

## Camera behavior

- Camera frames are processed only in memory and are never saved.
- The separate mirrored camera window displays pose guides and detected input.
- If tracking is lost, Pipin keeps running in the current lane.
- The player gets two seconds of collision grace after tracking disappears.
- Keyboard controls continue working when the camera is unavailable.

## Test

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

## Windows build

    .\scripts\build_windows.ps1

The packaged game is written to dist\pUSA Run\pUSA Run.exe. PyInstaller
packages are operating-system specific. Linux and macOS builds must be produced
and tested on their respective operating systems.

## Figma asset handoff

See assets/README.md for exact sizes, formats, and animation-frame guidance.
