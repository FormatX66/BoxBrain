# Ideas

- Capture a bounded region before and after each action and retain only hashes,
  dimensions, timestamps, and a short-lived redacted image when needed.
- Treat cursor metadata and framebuffer pixels as separate observation
  channels because some RDP servers render the cursor out of band.
- Add one deterministic Windows lab window with known text and coordinates for
  pointer and keyboard verification.
- Turn the verified Task Manager and Notepad launches into fixed regression
  scenarios.
- Build the native connector against both the pinned build version and the
  deployed Pi version until the toolchain is unified.
