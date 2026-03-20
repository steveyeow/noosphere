# Next Session: Frontend UX Redesign

## Context
Backend is complete. Frontend needs a significant UX rethink based on product discussions.

## Changes to Implement

### 1. Sidebar — Minimal Nav Only
Sidebar should only have navigation links, NO content:
```
⊙ Noosphere (logo → home)
──────────
[+ New]          ← goes to terminal-style creation page
📚 My Corpora    ← goes to corpus list/grid in CONTENT area
🌐 Network       ← goes to full network graph in CONTENT area  
──────────
[🌙 dark mode]
```
- My Corpora is a NAV LINK, not an expandable list in sidebar
- Network should be prominent, not buried at bottom
- Corpus items are NOT listed in the sidebar — they appear in the content area when "My Corpora" is clicked

### 2. Home / New Page — Terminal Style (like aigis-pay)
Reference: `/Users/steveyao/Projects/GitHub/aigispay.com/landingpage.html`

Terminal-style interactive demo showing:
```
> noosphere add "My AI Research Blog"
  Creating corpus... ✓
  Name: My AI Research Blog
  Access: Public
  
> noosphere write
  Opening editor...

> noosphere upload ./notes/*.md
  Uploading 12 files...
  Indexing... ✓
  
  MCP: http://localhost:8420/mcp
  API: http://localhost:8420/api/v1/corpora/abc123/search
  
  Your knowledge is now part of the Noosphere.
```

Below terminal: actual action buttons (Write / Upload / Import URL)

Key CSS from aigis-pay:
- `.terminal-demo` — dark bg (#1c1c1e), rounded corners (12px), box-shadow
- `.terminal-header` — dots (red/yellow/green) + title
- `.terminal-body` — monospace font (JetBrains Mono), padding 24px
- `.terminal-prompt` — `>` caret + blinking cursor (█)
- `.terminal-response` — gray text (#8b949e)
- Typing animation: character-by-character at 35ms intervals
- `@keyframes cursor-blink` + `@keyframes terminalFadeIn`

### 3. My Corpora — Content Area View
When "My Corpora" is clicked in sidebar, the content area shows:
- **List view** (default): cards/rows of your corpora with name, stats, access level, endpoints
- **Network view** (toggle): D3 graph showing ONLY your corpora as nodes
- Toggle switch between list and network at the top

### 4. Network — Full Noosphere
When "Network" is clicked:
- Full-screen D3 graph of ALL corpora (yours + registered from registry)
- Nodes are draggable (already implemented)
- Feynman-style composer at bottom: "Ask the Noosphere..."
- Click a node → goes to corpus detail

### 5. Corpus Detail
- Sources list (first auto-expanded)
- Chat composer at bottom (Feynman-style)
- Right panel: metadata, MCP/API endpoints, stats, access control

### 6. Composer Style (Feynman-style)
Already implemented. Key CSS:
- `border-radius: 24px`
- `padding: 14px 16px 8px`
- Transparent textarea, 16px font
- Round send button (32px, dark bg)
- Focus glow effect

## Files to Modify
- `noosphere/api/static/index.html`
- `noosphere/api/static/styles.css`
- `noosphere/api/static/app.js`

## Backend — No Changes Needed
All APIs are complete: chat, search, CRUD, upload, URL ingest, analytics, MCP, registry.
