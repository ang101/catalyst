# Catalyst UI

A browser-based interface for the [ang101/catalyst](https://github.com/ang101/catalyst) ML paper replication system built on ZeroClaw.

## What it does

- Accepts a paper by arXiv URL, DOI, title, or PDF upload
- Lets you configure your local machine specs (GPU, RAM, cores, disk)
- Simulates the ZeroClaw agent pipeline (preflight → acquire → extract → scout → plan → execute → report)
- Shows hardware gap analysis (radar chart, spec comparison)
- Shows task feasibility per replication step (horizontal bar chart)
- Shows live training loss curve (paper vs. reproduced)
- Shows metric discrepancy analysis with in/out-of-tolerance badges
- Shows cloud alternatives (bubble chart: cost vs. coverage)
- Has an AI chat window backed by the Anthropic API

## Setup

### 1. Get your API key

Go to [console.anthropic.com](https://console.anthropic.com) and create an API key.

### 2. Add your key

Open `assets/app.js` and replace line 10:

```js
const ANTHROPIC_API_KEY = 'YOUR_API_KEY_HERE';
```

with your actual key:

```js
const ANTHROPIC_API_KEY = 'sk-ant-api03-...';
```

> **Security note**: For production use, proxy the API call through your own backend instead of exposing the key client-side. See the [Anthropic docs](https://docs.anthropic.com) for server-side SDK usage.

### 3. Open in browser

Just open `index.html` directly — no build step needed:

```bash
open index.html        # macOS
start index.html       # Windows
xdg-open index.html    # Linux
```

Or serve locally with:

```bash
npx serve .
# or
python3 -m http.server 8080
```

## File structure

```
catalyst-ui/
  index.html          main interface
  assets/
    styles.css        all styling (dark mode aware)
    app.js            all logic, chart rendering, API calls
  README.md           this file
```

## Connecting to the real Catalyst backend

This UI simulates the ZeroClaw pipeline for demo purposes. To connect to a real running Catalyst instance:

1. Expose ZeroClaw's agent run endpoint (or write a thin HTTP wrapper around `zeroclaw agent -m "..."`)
2. Replace the `startRun()` simulation in `app.js` with a `fetch()` call to your backend
3. Stream the `agent-log` output from ZeroClaw's stdout
4. Parse `papers/<id>/results.json` and feed it into `buildResults()` for real metric discrepancy analysis

The output schema Catalyst produces (from its README):
```
papers/<id>/
  STATUS.json           checkpoint/resume state
  requirements.json     extracted requirements
  plan.json             execution plan
  scaling_rationale.md  scaling decisions
  runs/<ts>/
    results.json        captured metrics   ← feed into buildResults()
    output.log          training output    ← stream into agent-log
  summary.md            report
```

## Tailoring for your paper

The metric names and paper-reported values in `buildResults()` in `app.js` are set for LoRA (2106.09685). When running a different paper, update the `metrics` array in `buildResults()` with the actual claimed numbers from the paper's results table.

## License

MIT
