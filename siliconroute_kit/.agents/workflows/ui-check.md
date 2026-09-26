---
description: Open the dashboard in the browser agent, click every tab, screenshot, fix issues
---
1. Make sure the server is running at http://127.0.0.1:8000.
2. Open it with the browser agent. Visit tabs in order: Live, Benchmark, Analysis, Router, History, About.
3. On each tab: take a screenshot, check the browser console for errors, check that charts render with real data (or a clear empty state), that units are shown, and that "not available" pills appear where data is missing.
4. Check layout at 1280x720 and 1920x1080: no overlapping or cut-off text.
5. List every problem found with its screenshot, then fix them one by one (following .agents/rules/02-design.md).
6. Re-run steps 2-4 and attach the final screenshots in a walkthrough.
