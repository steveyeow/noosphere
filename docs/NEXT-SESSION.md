# Next Session: Terminal Polish — Copy AigisPay Dashboard Style

## Reference
AigisPay dashboard screenshot: `assets/image-cfe40437-3a4a-4e3e-87f8-80dc6f316e68.png`

The AigisPay dashboard has this exact layout that we need to replicate:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                   Evening, Alice                            │
│                       🤖                                    │
│               $4,087.75  $740 in escrow                     │
│            ● Bronze · 1 trade · 0x742b...                   │
│                                                       + New │
│─────────────────────────────────────────────────────────────│
│                                                             │
│  > █ Describe a trade, or pick one below                    │
│                                                             │
│    / for shortcuts                                          │
│                                                             │
│    > Sell a Steam account with 500 hours on CS2             │
│    > Trade in-game currency for 50 USDC                     │
│    > Freelance logo design, 3 revisions included            │
│    > Pay my driver $25 for an airport ride                  │
│                                                             │
│                                                             │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Exact Changes Needed

### 1. Sidebar logo font
- Change "Noosphere" in sidebar to Libre Baskerville (same as landing page hero)

### 2. Pixel icon redesign  
- Current one is too crude
- Needs to be cleaner, cuter — reference AigisPay's pixel robot quality
- Pixel art style, 8x8 or 10x10 grid, crisp edges

### 3. Header layout
- Icon CENTERED above greeting (like AigisPay: name centered, robot below)
- "Evening, [username]" — add username (hardcode for now)
- Stats below greeting: "3 corpora · 5 sources · 173 words"
- Divider line separating header from input area
- "+ New chat" button on the right side of the divider (like AigisPay's "+ New chat")

### 4. Terminal input
- `> █` with blinking cursor (the █ character with CSS animation)
- Placeholder: "Paste a URL, upload a file, or write something"
- Input area has clear visual separation from header

### 5. Suggestions — THREE main actions
```
/ for shortcuts

> Paste a link to import
> Upload a file  
> Write something
```
These are the 3 primary ways to add knowledge. NOT "Ask the Noosphere" or "/status" — those are secondary.

### 6. Greeting font
- "Evening" should use Libre Baskerville (serif) — same as landing page hero
- All terminal output uses JetBrains Mono (monospace)

### 7. History / New Chat
- Sidebar "+ New" should clear the terminal and reset to initial state
- Consider adding "/ for shortcuts" hint like AigisPay's "/ for shortcuts"

### 8. The AigisPay terminal CSS to reference
The AigisPay landing page has terminal styles at:
`/Users/steveyao/Projects/GitHub/aigispay.com/landingpage.html` (lines 430-591)

Key styles to copy:
- `.terminal-prompt` — font-family, font-size, color, line-height
- `.terminal-caret` — font-weight: 700, color
- `.terminal-cursor` — animation: cursor-blink 1.1s step-end infinite
- `.terminal-response` — color: #8b949e
- `.terminal-card` — border, background, border-radius
- `@keyframes cursor-blink` — 0%,100% opacity:0.6, 50% opacity:0

## Files to Modify
- `noosphere/api/static/app.js` — renderHome()
- `noosphere/api/static/styles.css` — terminal styles  
- `noosphere/api/static/index.html` — sidebar logo font
