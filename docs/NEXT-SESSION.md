# Next Session: Terminal UX Fix

## Critical Issues to Fix

### 1. Input position — TOP not bottom
Input should be at the TOP of the content area (like AigisPay), with output appearing BELOW and pushing down as more content appears. NOT chat-style bottom input.

```
┌──────────────────────────────────────────┐
│  🐲 Evening                              │  ← header with icon + stats
│  3 corpora · 5 sources · 173 words       │
├──────────────────────────────────────────┤
│  > █ Paste a URL or ask a question       │  ← INPUT at top
│                                          │
│  / for shortcuts                         │
│  > Import a URL                          │
│  > Write a new source                    │
│  > Ask the Noosphere                     │
├──────────────────────────────────────────┤
│  (output appears here and grows down)    │  ← OUTPUT below
│                                          │
└──────────────────────────────────────────┘
```

### 2. Remove multi-step corpus selection
URL import should NOT ask "Add to which corpus?" — it should auto-create or use a default corpus. Zero friction.

Flow: paste URL → fetch → index → done. One step.

### 3. Fix suggestions
- Remove `https://example.com/my-article` — it fails with SSL error
- Use real actionable suggestions that work

### 4. Pixel dragon redesign
Current one is too crude. Design a cleaner, cuter pixel character. Reference AigisPay's pixel robot quality level.

### 5. Stats position
Move stats to LEFT side under the dragon icon (like AigisPay shows balance under the robot), not right-aligned.

### 6. Remove subtitle
Remove "What will you add to the Noosphere?" — too verbose.

### 7. Clear/reset
Need a way to clear the terminal output and return to initial state.

## Reference
AigisPay dashboard screenshot: assets/image-cfe40437-3a4a-4e3e-87f8-80dc6f316e68.png

## Files to Modify
- `noosphere/api/static/app.js` — renderHome(), terminal interaction
- `noosphere/api/static/styles.css` — terminal layout (input top, output bottom)
- `noosphere/core/terminal.py` — remove corpus selection step, auto-create
