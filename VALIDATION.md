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
