# Validation record

Prepared 13 November 2026.

## Completed

- Python syntax checks for the server, optional vision adapter, and browser smoke test.
- JavaScript syntax check with Node.js.
- Eleven automated aiohttp server tests passed:
  1. Role authorization and hidden result visibility.
  2. Server deadlines, stale round rejection, and one saved vote per credential.
  3. Settings and custom scenario validation.
  4. Automatic round opening, closing, and revealing.
  5. Detection triggers, simulation labels, and cooldown.
  6. Stale feed protection for detection-triggered prompts.
  7. Ending sessions clears image data and blocks new actions.
  8. Frame upload authorization and stale-frame retrieval.
  9. Export authorization and exclusion of credentials.
  10. Authenticated Server-Sent Events and participant presence.
  11. Cross-origin mutation rejection.

## Not verified in the build environment

- Visual layout and end-to-end browser execution: Chromium was present, but the environment denied the Unix socket operation required to launch it. `tests/browser_smoke.py` is included for running the complete flow locally.
- Real OpenCV inference: the optional OpenCV package was not installed, and the environment could not retrieve it. Three real-model tests are included and skip automatically until the vision dependencies are installed. Synthetic trigger tests do not verify actual person detection quality.
- Physical camera capture, mobile Safari, HTTPS deployment, Docker build, and audience-scale network performance.

The browser interface, camera integration, and real detector adapter are implemented; this record distinguishes implementation from tests actually completed. Test the intended camera scene and network before a live presentation.

## Panic simulation update ? 22 November 2026

- Python suite: 19 passed, 3 optional vision tests skipped.
- Node.js suite: 9 passed, covering camera setup, browser audio activation, one siren loop per device, local mute, hidden-tab silence, and shared alert/session cleanup.
- JavaScript syntax check passed.
- Server checks cover manager authorization, shared panic state, stopping and replaying, session ending, and blocking new automatic/detection/manual rounds during panic.
- The browser smoke script now checks shared emergency visuals, presenter-only stop controls, local audio interaction, stopping, and replay. It could not run in this environment because the Playwright Python package is not installed. Browser layout and audible siren playback still require a local check.

## Live vision setup - 22 November 2026

- Installed the vision requirements in the ignored project `.venv`, including OpenCV and NumPy.
- All 22 Python tests passed in that environment, including the three real detector tests previously skipped.
- Started a separate HTTPS instance on port 8444 using the existing certificate; `/api/health` returned `vision: true`.
- Uploaded an OpenCV pedestrian test image through the actual camera-frame API. The running model returned two person detections with `simulated: false` and the matching frame sequence. This verifies positive inference and delivery, not counting accuracy across a classroom or arbitrary camera scenes.
- Confirmed the scripted panic mode can run alongside real model observations. The model does not produce the scripted criminal accusations.
- Added `start-vision.ps1` to launch the HTTPS app with vision enabled using the project environment. Physical-camera and classroom detection quality still require an on-device check.
- Positive-inference sample: https://github.com/opencv/opencv_extra/blob/4.x/testdata/cv/cascadeandhog/images/image_00000000_0.png (downloaded only into the ignored `.venv` for verification).

## Close-up face detection update - 22 November 2026

- Replaced full-body HOG detection with the bundled MIT-licensed YuNet ONNX face detector; model provenance and checksum are in `models/README.md`.
- Updated live observations and overlays to face labels, face counts, and detection scores. Synthetic demo mode retains simulated people. Camera inference is sampled every 0.5 seconds when processing capacity permits.
- All 25 Python tests and 9 Node.js tests passed. Coverage includes tiny/blank/invalid images, normalized/clipped face boxes, JSON serialization, and face observation fields.
- Restarted the separate HTTPS demo instance on port 8444. Health reports `visionModel: OpenCV YuNet`.
- Verified positive inference on two OpenCV sample images. Uploaded a close-up portrait through the running camera-frame API and received one real face box and a face count of one. Confirmed face observations coexist with the scripted panic mode.
- Source samples: https://github.com/opencv/opencv_extra/blob/4.x/testdata/cv/cascadeandhog/images/audrybt1.png and https://github.com/opencv/opencv/blob/4.x/samples/data/lena.jpg. These were downloaded only into the ignored `.venv` for verification.
- No physical-camera or classroom accuracy evaluation was performed. Face detection does not identify people; the panic accusations remain scripted.
