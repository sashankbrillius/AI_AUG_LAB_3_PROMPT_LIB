# Lab 3: Build Your DevOps Prompt Library — Mega-Lab

**Duration:** 30-45 minutes
**Mode:** Mock (no API keys needed — works fully with simulated LLM responses)
**Topics Covered:** Prompt engineering for DevOps, prompt quality scoring, template testing, library management, token economics

---

## Scenario: SmartDine's Prompt Chaos

SmartDine's platform team of 12 engineers each writes their own prompts for debugging, incident analysis, and automation. When a P1 incident hits at 2 AM, the on-call engineer scrambles to craft a good prompt from scratch — under pressure, half-asleep, with no template to start from.

Here is what keeps going wrong:

1. **Inconsistent prompt quality** — One engineer writes a 5-component production prompt that produces structured JSON output. Another writes "analyze this log" and gets a rambling paragraph. Same incident, wildly different analysis quality.

2. **No reuse across the team** — Every engineer reinvents the wheel. The excellent RCA prompt that saved 45 minutes during last month's outage lives in one person's shell history, unknown to everyone else.

3. **No quality standards** — Nobody knows if a prompt is "good enough" until it fails in production. There is no scoring, no testing, no threshold for what makes a prompt production-ready.

4. **Token waste adds up** — Verbose prompts with unnecessary context cost 3-5x more in API tokens. At SmartDine's scale (200+ incidents/year, dozens of daily automation runs), this burns through budget.

Your job: Build a team-shared prompt library with 20 tested, quality-scored templates across 5 DevOps categories, test them against realistic scenarios, and export the library as a reusable resource your team can adopt immediately.

---

## Getting Started

### 1 — Start the Lab

```bash
cd lab3-devops-prompt-library
docker compose up -d --build
```

Wait about 30 seconds, then verify everything is running:

```bash
curl -s http://localhost:7000/health | python3 -m json.tool
```

You should see `"ok": true`, `"mode": "mock"`, and `"prompts_in_library": 20`.

### 2 — Check Current Configuration

```bash
curl -s http://localhost:7000/config | python3 -m json.tool
```

**What to observe:**
- `mode` — "mock" (LLM responses are simulated — no API key needed)
- `prompt_quality_threshold` — 0.6 (minimum quality score to pass — we will tune this later)
- `export_format` — "yaml" (default export format — we will switch to markdown later)
- `prompts_in_library` — 20 (pre-seeded templates across 5 categories)
- `scenarios_available` — 5 (one test scenario per category)
- `categories` — The 5 DevOps prompt categories

### 3 — Open Grafana

Open http://localhost:3000 in your browser (login: `admin` / `admin`, skip password change). You should see the **Lab 3 — SmartDine DevOps Prompt Library Dashboard** with 13 panels. Most panels will show "No data" until you start running commands.

### Troubleshooting — Getting Started

| Problem | Cause | Fix |
|---------|-------|-----|
| `docker compose up` fails | Docker daemon not running | Run `sudo systemctl start docker` and retry |
| Port 7000/9090/3000 already in use | Another lab using the port | Run `docker ps` to find the conflict, then `docker stop <container_id>` |
| Health check returns "Connection refused" | Service still starting | Wait 30-60 seconds and retry; run `docker compose logs prompt-library` for errors |
| Grafana shows "No data" | Expected before running commands | Panels populate as you work through the lab |

---

## Part 1 — Browse the Prompt Library

**Goal:** Explore the pre-seeded library of 20 DevOps prompt templates across 5 categories.

### Why This Matters

A prompt library is the DevOps equivalent of a runbook collection. Just as you would never expect an on-call engineer to write a runbook from scratch during an incident, you should not expect them to craft a quality prompt from scratch at 2 AM. Pre-built, tested templates mean faster response, consistent quality, and less cognitive load under pressure.

The 5 categories cover the full DevOps lifecycle:
- **Debugging** (4 prompts) — Log analysis, error triage, dependency tracing, performance bottlenecks
- **RCA** (4 prompts) — Incident timelines, root cause identification, blast radius mapping, remediation planning
- **Infrastructure Explanation** (4 prompts) — Architecture diagrams, config audits, capacity planning, cost analysis
- **Script Generation** (4 prompts) — Monitoring setup, deployment automation, backup scripts, alerting rules
- **Postmortems** (4 prompts) — Blameless writeups, action item extraction, SLO impact reports, stakeholder communications

### 1.1 — List All Prompts

```bash
curl -s http://localhost:7000/prompts | python3 -m json.tool
```

**What to observe:**
- `total` — 20 prompts in the library
- `category_breakdown` — 4 prompts per category, evenly distributed
- Each prompt shows its `id`, `name`, `description`, and `tags`
- Notice how prompt names are action-oriented (e.g., "Log Analysis Debugger", "Blast Radius Mapper")

### 1.2 — Filter by Category

```bash
curl -s "http://localhost:7000/prompts?category=debugging" | python3 -m json.tool
```

**What to observe:**
- `total` — 4 debugging prompts
- Templates cover log analysis, error triage, dependency tracing, and performance bottleneck identification
- Each addresses a different debugging challenge

Try other categories:

```bash
curl -s "http://localhost:7000/prompts?category=rca" | python3 -m json.tool
curl -s "http://localhost:7000/prompts?category=postmortems" | python3 -m json.tool
```

### 1.3 — View a Prompt in Detail

```bash
curl -s http://localhost:7000/prompts/debug-log-analysis | python3 -m json.tool
```

**What to observe:**
- `prompt.prompt` — The full 5-component prompt template (Role, Task, Input, Constraints, Output Format)
- `prompt.variables` — Placeholders like `{log_data}` that get filled with real data
- `quality_analysis.score` — Automated quality score (should be 1.0 for a well-structured template)
- `quality_analysis.components_detected` — Which of the 5 prompt components are present
- `quality_analysis.quality_level` — "full_production" means all 5 components detected

### 1.4 — View a Postmortem Prompt

```bash
curl -s http://localhost:7000/prompts/postmortem-blameless-writeup | python3 -m json.tool
```

**What to observe:**
- The Role specifies "blameless postmortem facilitator following Google's SRE guidelines"
- Constraints include "Never name individuals — use roles" and "Include what went well"
- This is the kind of prompt that saves 30-60 minutes of manual postmortem writing

### Troubleshooting — Part 1

| Problem | Cause | Fix |
|---------|-------|-----|
| `total: 0` | Service not initialized | Restart: `docker compose restart prompt-library` |
| Prompt detail returns 404 | Wrong prompt ID | Use GET /prompts to see valid IDs |
| Quality score is 0 | Prompt text is empty or malformed | Check the prompt field in the response |

---

## Part 2 — Test Prompts Against Scenarios

**Goal:** Run prompt templates against realistic SmartDine scenarios and see how they perform with quality scores and mock LLM responses.

### Why This Matters

A prompt template is only as good as its performance under realistic conditions. Testing against scenarios answers: Does this prompt produce the right kind of output? Does it score high enough on quality? Would it work if handed to a real LLM with real incident data? The 5 test scenarios simulate common DevOps situations using SmartDine's payment outage as a recurring theme.

### 2.1 — List Available Scenarios

```bash
curl -s http://localhost:7000/scenarios | python3 -m json.tool
```

**What to observe:**
- 5 scenarios, one per category
- Each has a SmartDine-themed description (payment timeouts, deployment rollbacks, K8s config reviews, monitoring setup, Friday outage postmortem)

### 2.2 — View a Scenario's Full Context

```bash
curl -s http://localhost:7000/scenarios/scenario-debugging | python3 -m json.tool
```

**What to observe:**
- `context` — The realistic log data and error messages that get fed to the prompt
- `expected_keywords` — What a good response should mention (connection pool, timeout, cascade, etc.)
- This is the data the prompt will "analyze" when tested

### 2.3 — Test a Debugging Prompt

```bash
curl -s -X POST http://localhost:7000/prompts/test \
  -H "Content-Type: application/json" \
  -d '{"prompt_id": "debug-log-analysis", "scenario_id": "scenario-debugging"}' \
  | python3 -m json.tool
```

**What to observe:**
- `test_result` — "pass" or "fail" (based on quality threshold)
- `quality_score` — How well the prompt is structured (0.0-1.0)
- `consistency_score` — How likely the prompt is to produce consistent results
- `relevance_score` — How many expected keywords appear in the mock response
- `mock_response` — What the LLM would return (simulated)
- `tokens_used` — Prompt vs completion tokens (cost tracking)
- `analysis` — Plain-language explanation of the findings

### 2.4 — Test an RCA Prompt

```bash
curl -s -X POST http://localhost:7000/prompts/test \
  -H "Content-Type: application/json" \
  -d '{"prompt_id": "rca-root-cause", "scenario_id": "scenario-rca"}' \
  | python3 -m json.tool
```

**What to observe:**
- The RCA prompt uses the 5 Whys technique
- `mock_response.five_whys` — Shows each level of "why" with evidence
- `mock_response.category` — Classifies the root cause type (config-change)
- Compare the token usage with the debugging prompt — different prompts have different costs

### 2.5 — Test a Weak Prompt (Custom Text)

```bash
curl -s -X POST http://localhost:7000/prompts/test \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "analyze this log", "scenario_id": "scenario-debugging"}' \
  | python3 -m json.tool
```

**What to observe:**
- `quality_score` — Much lower than the library templates
- `quality_level` — "minimal" or "bare_minimum" (missing most components)
- `test_result` — Likely "fail" (below the quality threshold)
- `consistency_score` — Lower, meaning results would vary between runs
- This demonstrates why structured templates matter — a vague prompt produces unreliable results

### Troubleshooting — Part 2

| Problem | Cause | Fix |
|---------|-------|-----|
| Test returns 404 | Invalid prompt_id or scenario_id | Use GET /prompts and GET /scenarios for valid IDs |
| `test_result` is always "pass" | Threshold too low | This is expected with the default 0.6 threshold; we will raise it later |
| Token counts seem low | Mock mode estimates tokens | In live mode with a real API key, actual token counts appear |

---

## Part 3 — Score Prompt Quality

**Goal:** Use the quality scoring engine to analyze prompts and understand what makes a prompt production-ready.

### Why This Matters

The difference between a "good" prompt and a "production" prompt is measurable. Lesson 18 taught the 5 core prompt components (Role, Task, Input, Constraints, Output Format). The quality scorer detects which components are present and assigns a score. This is not subjective — it is a checklist that any team can agree on and enforce.

### 3.1 — Score a Bare Minimum Prompt

```bash
curl -s -X POST http://localhost:7000/prompts/score \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "What is wrong with the server?"}' \
  | python3 -m json.tool
```

**What to observe:**
- `score` — Very low (0.0-0.2)
- `quality_level` — "bare_minimum"
- `components_detected` — Most or all are `false`
- `suggestions` — Specific recommendations for improvement (add Role, add Task, etc.)

### 3.2 — Build Up a Prompt Component by Component

Start with Role only:

```bash
curl -s -X POST http://localhost:7000/prompts/score \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "You are a senior SRE. What is wrong with the server?"}' \
  | python3 -m json.tool
```

Add Task:

```bash
curl -s -X POST http://localhost:7000/prompts/score \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "You are a senior SRE. Analyze these logs and identify the root cause of the server failure."}' \
  | python3 -m json.tool
```

Add Input and Constraints:

```bash
curl -s -X POST http://localhost:7000/prompts/score \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "Role: You are a senior SRE.\nTask: Analyze these logs and identify the root cause.\nInput: {log_data}\nConstraints: Focus only on ERROR entries. Do not speculate."}' \
  | python3 -m json.tool
```

Add Output Format (complete prompt):

```bash
curl -s -X POST http://localhost:7000/prompts/score \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "Role: You are a senior SRE.\nTask: Analyze these logs and identify the root cause.\nInput: {log_data}\nConstraints: Focus only on ERROR entries. Do not speculate.\nOutput Format: JSON with fields: root_cause, severity, affected_services"}' \
  | python3 -m json.tool
```

**What to observe across these 4 calls:**
- Score increases from ~0.2 to 1.0 as components are added
- `quality_level` progresses: bare_minimum → minimal → developing → full_production
- `suggestions` list gets shorter as you add each component
- The final 5-component prompt passes the quality threshold

### 3.3 — Score All Library Prompts at Once

```bash
curl -s http://localhost:7000/stats | python3 -m json.tool
```

**What to observe:**
- `quality_summary.average_score` — The average quality across all 20 prompts
- `quality_summary.passing_count` — How many prompts pass the current threshold
- `quality_summary.threshold` — The current threshold (0.6)
- All 20 pre-seeded prompts should pass because they are well-structured templates

### Troubleshooting — Part 3

| Problem | Cause | Fix |
|---------|-------|-----|
| Score does not change when adding components | Component keyword not detected | Use exact keywords: "Role:", "Task:", "Constraints:", "Output Format:" |
| All prompts show same score | Quality scorer is deterministic | This is expected — same prompt always gets same score |
| Suggestions are empty | All components detected | This means the prompt is well-structured |

---

## Part 4 — Export the Library

**Goal:** Export the full prompt library as YAML and Markdown for team sharing and version control.

### Why This Matters

A prompt library only has value if the team can access it. Exporting as YAML means you can check it into Git alongside your runbooks and infrastructure-as-code. Exporting as Markdown gives you a human-readable reference document. Both formats make the library a team asset rather than tribal knowledge.

### 4.1 — Export as YAML (Default)

```bash
curl -s http://localhost:7000/export | head -40
```

**What to observe:**
- Structured YAML with metadata (title, version, export timestamp)
- Prompts organized by category
- Each prompt includes its quality score and quality level
- This format is ideal for Git storage and programmatic consumption

### 4.2 — Export as Markdown

```bash
curl -s "http://localhost:7000/export?format=markdown" | head -60
```

**What to observe:**
- Formatted Markdown with headers, code blocks, and metadata
- Human-readable — suitable for a team wiki, Confluence page, or README
- Each prompt shows its quality score, tags, and variables
- This is the version you would share in a Slack channel or team onboarding doc

### 4.3 — Save the Export to a File

```bash
curl -s http://localhost:7000/export > my-prompt-library.yaml
echo "Saved $(wc -l < my-prompt-library.yaml) lines to my-prompt-library.yaml"

curl -s "http://localhost:7000/export?format=markdown" > my-prompt-library.md
echo "Saved $(wc -l < my-prompt-library.md) lines to my-prompt-library.md"
```

**What to observe:**
- Both files are ready to commit to your team's Git repository
- The YAML file can be loaded programmatically by automation tools
- The Markdown file can be rendered in GitHub, GitLab, or any wiki

### Troubleshooting — Part 4

| Problem | Cause | Fix |
|---------|-------|-----|
| Export returns empty | Service not running | Run `docker compose logs prompt-library` to check |
| YAML is malformed | Unexpected characters in prompts | Check for unescaped special characters in custom prompts |
| Markdown formatting looks wrong | Viewing raw text | Open the .md file in a Markdown renderer (GitHub, VS Code preview) |

---

## Part 5 — Prometheus Metrics & Grafana Dashboard

**Goal:** Explore the observability metrics that the prompt library gateway exposes and see them visualized in Grafana.

### Why This Matters

Even your prompt management pipeline needs observability. How many prompts are being tested? What is the average quality score? How many tokens are being consumed? Which categories get the most usage? These meta-metrics help you understand prompt adoption, identify quality issues, and track LLM cost.

### 5.1 — Query Prometheus Directly

```bash
curl -s "http://localhost:9090/api/v1/query?query=prompts_library_total" \
  | python3 -m json.tool
```

**What to observe:**
- Shows the current number of prompts in the library (20)

```bash
curl -s "http://localhost:9090/api/v1/query?query=prompt_tests_total" \
  | python3 -m json.tool
```

**What to observe:**
- Test counts broken down by category and result (pass/fail)
- Each call to `/prompts/test` increments this counter

```bash
curl -s "http://localhost:9090/api/v1/query?query=prompt_token_estimate_total" \
  | python3 -m json.tool
```

**What to observe:**
- Token usage tracked by direction (prompt vs completion)
- In mock mode, tokens are estimated; in live mode, actual usage is recorded

### 5.2 — View the Grafana Dashboard

Open http://localhost:3000 and navigate to the **Lab 3 — SmartDine DevOps Prompt Library Dashboard**.

**What to observe across the 13 panels:**

**Row 1 — Gateway Performance:**
- **Request Rate by Endpoint** — Requests/sec to each endpoint (/prompts, /prompts/test, /export)
- **Gateway Latency (p50/p95)** — Response time distribution for all API calls
- **Error Rate (5xx %)** — Gateway error rate (should be 0% under normal operation)

**Row 2 — Prompt Quality & Testing:**
- **Prompt Tests by Category** — Test operations broken down by category and pass/fail result
- **Quality Score by Category (p50/p95)** — Quality score distribution per category
- **Category Usage Distribution** — Which categories are being used most

**Row 3 — Token Economics:**
- **Token Estimates (Cost Proxy)** — Cumulative token usage over the last hour
- **Token Burn Rate (per minute)** — Token velocity — how fast you are consuming LLM capacity
- **Library Exports by Format** — How many times the library has been exported (YAML vs Markdown)

**Row 4 — Status Gauges:**
- **Prompts in Library** — Current prompt count (20 + any you add)
- **Total Tests Run** — Lifetime test count
- **Total Tokens Used** — Lifetime token consumption
- **Quality Threshold** — Current quality threshold setting

### Troubleshooting — Part 5

| Problem | Cause | Fix |
|---------|-------|-----|
| Prometheus query returns empty | Metrics not yet generated | Run through Parts 1-4 first to generate metrics |
| Grafana panels show "No data" | Prometheus datasource not connected | Check Grafana > Settings > Data Sources > Prometheus URL is `http://prometheus:9090` |
| Token panels are flat | No tests run yet | Run some prompt tests (Part 2) to see token counters increment |

---

## Linux File Editing Quick Reference

Since this lab runs inside a Linux VM, you will use terminal-based editors to modify files. Here are the two most common options:

**Option A — nano (recommended for beginners):**
```bash
nano <filepath>
```
- Navigate with arrow keys to the line you need to edit
- Make your changes directly
- Press `Ctrl+O` then `Enter` to save
- Press `Ctrl+X` to exit

**Option B — vi/vim (for experienced users):**
```bash
vi <filepath>
```
- Press `i` to enter Insert mode
- Navigate to the target line and make your edit
- Press `Esc` to exit Insert mode
- Type `:wq` and press `Enter` to save and exit
- To exit WITHOUT saving: press `Esc`, type `:q!`, press `Enter`

**Helpful commands:**
```bash
# Find the exact line number before editing:
grep -n "search_text" <filepath>

# Show a file with line numbers:
cat -n <filepath> | head -20

# Jump directly to a line in nano:
nano +8 <filepath>

# Jump directly to a line in vi:
vi +8 <filepath>
```

---

## Part 6 — Manual Edits

Now make two configuration changes to see how quality threshold and export format affect the prompt library pipeline.

### Edit 1: Raise the Quality Threshold (Stricter Standards)

The current threshold is `0.6`, which is relatively lenient — most prompts pass easily. Raise it to `0.8` to enforce stricter quality standards, which is closer to what a production team should require.

> **Editing tip:** Open the file with `nano +8 .env` or `vi +8 .env` to jump directly to the line.

**File:** `.env`
**Find (line 8):**
```
PROMPT_QUALITY_THRESHOLD=0.6
```

**Change to:**
```
PROMPT_QUALITY_THRESHOLD=0.8
```

### Edit 2: Change the Export Format (YAML to Markdown)

The current export format is `yaml`. Change to `markdown` so the default export produces a human-readable document suitable for team wikis and onboarding guides.

> **Editing tip:** Open the file with `nano +11 .env` or `vi +11 .env` to jump directly to the line.

**File:** `.env`
**Find (line 11):**
```
EXPORT_FORMAT=yaml
```

**Change to:**
```
EXPORT_FORMAT=markdown
```

### Restart and Verify

```bash
docker compose up -d prompt-library
```

Wait 10 seconds, then verify:

```bash
curl -s http://localhost:7000/config | python3 -m json.tool | grep -E '"prompt_quality_threshold|export_format"'
```

You should see `"prompt_quality_threshold": 0.8` and `"export_format": "markdown"`.

### Test the Impact

**Test a prompt with the new stricter threshold:**

```bash
curl -s -X POST http://localhost:7000/prompts/test \
  -H "Content-Type: application/json" \
  -d '{"prompt_text": "You are an SRE. Analyze these logs and identify the root cause. Focus only on ERROR entries.", "scenario_id": "scenario-debugging"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Score: {d[\"quality_score\"]}  Threshold: {d[\"threshold\"]}  Result: {d[\"test_result\"]}')"
```

**What to observe:**
- With the threshold at 0.8, this 3-component prompt now **fails** (it has Role, Task, and Constraints — but no Input or Output Format)
- At 0.6 it would have passed — the higher threshold enforces stricter standards
- This forces engineers to write prompts with all 5 components to pass

**Test the default export format change:**

```bash
curl -s http://localhost:7000/export | head -5
```

**What to observe:**
- Output is now Markdown (starts with `# SmartDine DevOps Prompt Library`) instead of YAML
- The team gets a human-readable document by default

### Troubleshooting — Part 6

| Problem | Cause | Fix |
|---------|-------|-----|
| Config still shows old values | Restart did not pick up .env changes | Run `docker compose down && docker compose up -d` for a full restart |
| Threshold change has no effect | Wrong line edited | Check `cat -n .env` to verify line 8 shows the new value |
| Export format unchanged | Typo in value | Must be exactly `markdown` (lowercase, no spaces) |

---

## Key Takeaways

| Before (No Prompt Library) | After (With Prompt Library) |
|---|---|
| Each engineer writes prompts from scratch | 20 pre-built, tested templates ready to use |
| No quality standards for prompts | Quality scoring with configurable threshold (0.6 → 0.8) |
| No testing before production use | Test against realistic scenarios with pass/fail results |
| Prompts live in shell history (tribal knowledge) | Exportable YAML/Markdown for Git and team wikis |
| No visibility into prompt usage or costs | Prometheus metrics + Grafana dashboard (13 panels) |
| Inconsistent outputs across engineers | 5-component structure (Role, Task, Input, Constraints, Output Format) |
| Token waste from verbose prompts | Token estimation shows cost impact of each prompt |
| No categories or organization | 5 categories: debugging, RCA, infra, scripts, postmortems |

---

## Cleanup

```bash
docker compose down -v
```

This removes all containers and volumes. Your exported YAML/Markdown files (if saved) remain on disk.
