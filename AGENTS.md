# Agent Notes

## Browser Usage

- The local web app is served at `http://127.0.0.1:8765`.
- When checking or operating the app in a browser, first look for an existing browser tab whose URL starts with `http://127.0.0.1:8765`.
- If that tab already exists, reuse it and navigate within that same tab as needed.
- Do not open a new browser tab or a separate browser instance for routine app checks when the `8765` tab is already open.
- Only create a new browser tab when no `8765` tab exists.
- If the local service is not running, start the app service first, then open `http://127.0.0.1:8765`.

## Runtime Boundary

- Keep browser verification on the existing local app session whenever possible, because it may contain the current agreement state, login state, and UI context.
- Do not change the user's active browser flow unless the task specifically requires it.
