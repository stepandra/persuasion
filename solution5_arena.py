"""
Solution 5: Anchoring + Iterative Optimization with Real Arena Evaluation

Combines Solution 4's anchoring-seeded mutation loop with live submissions
to optimizationarena.com. Submits via Chrome DevTools (browser-based auth).

Prerequisites:
1. Chrome open with DevTools MCP connected
2. Logged into optimizationarena.com via X in that browser
3. ANTHROPIC_API_KEY env var set (for pitch generation via local proxy)

Usage: uv run solution5_arena.py
"""

import json
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ROUNDS = 50
CANDIDATES_PER_ROUND = 3
COOLDOWN = 65            # seconds between submissions
MODEL = "gemini-3.1-pro-preview"
ARENA_BASE = "https://www.optimizationarena.com"
RESULTS_FILE = "arena_results.tsv"

ARENA_PERSONAS = [
    {"name": "Marcus", "age": 19, "occupation": "College student", "city": "Austin, TX"},
    {"name": "Diane", "age": 72, "occupation": "Retired librarian", "city": "Savannah, GA"},
    {"name": "Raj", "age": 34, "occupation": "Software engineer", "city": "Seattle, WA"},
    {"name": "Gabriella", "age": 28, "occupation": "Graphic designer and calligraphy artist", "city": "Brooklyn, NY"},
    {"name": "Tom", "age": 55, "occupation": "Cattle rancher", "city": "Billings, MT"},
    {"name": "Priya", "age": 41, "occupation": "Cardiac surgeon", "city": "Chicago, IL"},
    {"name": "Jordan", "age": 23, "occupation": "Barista and aspiring musician", "city": "Portland, OR"},
    {"name": "Patricia", "age": 67, "occupation": "Retired federal judge", "city": "Washington, DC"},
    {"name": "Derek", "age": 45, "occupation": "High school football coach and history teacher", "city": "Birmingham, AL"},
    {"name": "Mei", "age": 31, "occupation": "Corporate attorney", "city": "San Francisco, CA"},
    {"name": "Hank", "age": 82, "occupation": "Retired postal worker", "city": "Duluth, MN"},
    {"name": "Zara", "age": 26, "occupation": "Social media influencer and marketing freelancer", "city": "Miami, FL"},
    {"name": "William", "age": 50, "occupation": "Small business owner, hardware store", "city": "Omaha, NE"},
    {"name": "Aisha", "age": 38, "occupation": "Elementary school art teacher", "city": "Albuquerque, NM"},
    {"name": "Vincent", "age": 60, "occupation": "Architect", "city": "Denver, CO"},
]

# ---------------------------------------------------------------------------
# Arena submission via browser fetch (uses existing auth session)
# ---------------------------------------------------------------------------

def submit_via_browser_js(pitch: str) -> str:
    """
    Returns JavaScript that submits a pitch via fetch() and collects SSE results.
    Run this in the browser via Chrome DevTools evaluate_script.
    """
    escaped = pitch.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f"""
async () => {{
    const resp = await fetch("/api/persuasion/submit-stream", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{description: "{escaped}"}})
    }});
    if (!resp.ok) {{
        return {{error: true, status: resp.status, text: await resp.text()}};
    }}
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;
    let evaluations = [];
    while (true) {{
        const {{done, value}} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {{stream: true}});
        const lines = buffer.split("\\n");
        buffer = lines.pop();
        for (const line of lines) {{
            if (!line.startsWith("data: ")) continue;
            const dataStr = line.slice(6);
            if (dataStr === "[DONE]") continue;
            try {{
                const data = JSON.parse(dataStr);
                if (data.type === "evaluation") {{
                    evaluations.push(data);
                }} else if (data.type === "complete" && data.submission) {{
                    result = data.submission;
                }} else if (data.success && data.submission) {{
                    result = data.submission;
                }} else if (data.errors) {{
                    return {{error: true, errors: data.errors}};
                }}
            }} catch(e) {{}}
        }}
    }}
    if (result) {{
        result._evaluations = evaluations;
    }}
    return result || {{error: true, message: "no result", evaluations}};
}}
"""


def fetch_submission_js(submission_id: str) -> str:
    return f"""
async () => {{
    const resp = await fetch("/api/persuasion/submissions/{submission_id}");
    return await resp.json();
}}
"""


# ---------------------------------------------------------------------------
# Pitch generation
# ---------------------------------------------------------------------------

def generate_mutations(best_pitch: str, best_median: float, round_num: int,
                       history: list[dict], n: int = CANDIDATES_PER_ROUND) -> list[str]:
    import anthropic
    client = anthropic.Anthropic(base_url="http://localhost:8317")

    history_lines = []
    for h in sorted(history, key=lambda x: x["median"], reverse=True)[:15]:
        persona_info = ""
        if h.get("evaluations"):
            low = sorted(h["evaluations"], key=lambda e: e["price"])[:3]
            persona_info = " | lowest: " + ", ".join(e["name"] + "=$" + str(e["price"]) for e in low)
        history_lines.append(f'  median ${h["median"]:.1f}{persona_info} | "{h["pitch"]}"')
    history_text = "\n".join(history_lines) if history_lines else "  (none yet)"

    is_late_round = round_num >= MAX_ROUNDS - 2

    prompt = f"""You are optimizing a 140-character sales pitch for a PEN on a store shelf.
Score = MEDIAN willingness to pay across 15 AI personas. #1 leaderboard = $425 median.

**Current best** (median ${best_median:.1f}):
"{best_pitch}"

**History** (best first):
{history_text}

**KNOWLEDGE GRAPH — What we know about each persona:**

IMMOVABLE FLOOR (accept $0.50-$3.50, can't fix):
- Hank (82, retired postal worker): Bic loyalist, $0.50-$2.50 always. Ignore him.
- Marcus (19, college student): Budget-locked $1.50-$3.50. Ignore him.

RESISTANT FLOOR ($1-$8, movable to $8-$15 max):
- Derek (45, coach/teacher): Best=$8.50 with "heirloom/grandfather". HATES "executive" framing ($1.25).
- William (50, hardware store): Best=$8.50 with "EDC liquidation". Thinks in wholesale.

SWING LOW ($2.50-$12.50):
- Tom (55, rancher): Best=$12.50 with Swiss/titanium. Respects TOOLS not luxury.

*** CRITICAL SWING TIER — these determine the median: ***
- Raj (34, software eng): Range $3.50-$45. BEST with "aircraft titanium/precision-milled" ($45).
  WORST with "estate liquidation/Japanese artisan" ($3.50) — sees through fake scarcity.
  Responds to: engineering materials, precision. NOT: marketing, scarcity, executive.
  #1 LEADERBOARD gets Raj to $425. We need to 10x his response.
- Aisha (38, art teacher): Range $4.50-$45. BEST with craftsmanship/museum-quality ($45).
  WORST with "executive/signature" ($4.50). Responds to: art, craft, quality tools.
- Jordan (23, barista/musician): Range $8.50-$45. BEST with "50-year lifespan" ($45).
  Eco-conscious, values sustainability + refillable. HATES clickbait framing.

RELIABLE MID ($18-$185):
- Zara (26, influencer): $18-$85. Instagram-worthy premium matters. Best at $85 w/ Swiss titanium.
- Gabriella (28, designer): $18-$185. Best=$185 with "investment grade 18k gold". Art/materials.

LUXURY ($28-$850+):
- Diane (72, librarian): Best=$425 with "investment grade 18k gold heirloom". Heritage matters.
- Vincent (60, architect): Best=$525 with investment grade. Precision + premium materials.
- Patricia (67, judge): Best=$850 with "Rolex of writing / Geneva / platinum". Swiss prestige.
- Mei (31, attorney): Best=$850 with Geneva/platinum/Rolex. Professional luxury.
- Priya (41, surgeon): Best=$850 with Swiss/titanium. Highest consistent payer.

**PROVEN STRATEGIES:**
WORKS: Swiss precision + rare materials + craftsmanship → $45 median
WORKS: Investment grade + precious metals + appraised value → $45 median, $234 mean
FAILS: Military/tactical → $28 (kills luxury buyers)
FAILS: Executive/professional → $8.50 (alienates non-professionals)
FAILS: Clickbait/WARNING → $8.50 (feels manipulative)
FAILS: Fake scarcity/estate liquidation → $18.50 (Raj sees through it)

**MEDIAN MATH:**
To hit $200+: need 8 of 15 at $200+. That means Raj+Jordan+Zara + all 5 luxury = 8. ✓
Key: get Raj from $45→$200+ AND Jordan from $45→$200+ AND Zara from $85→$200+.
If we crack these 3, median jumps to $200+ even with 7 people below.

**Round {round_num}/{MAX_ROUNDS}**
{"LATE ROUND: Try at least 1 radical departure." if is_late_round else ""}

Generate {n} pitches <=140 chars. Each must try a DIFFERENT angle to crack Raj+Jordan+Zara.
Respond with ONLY a JSON array of strings."""

    response = client.messages.create(
        model=MODEL, max_tokens=500, temperature=0.9,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        pitches = json.loads(text)
        valid = [p for p in pitches if isinstance(p, str) and len(p) <= 140]
        return valid[:n]
    except json.JSONDecodeError:
        print(f"  [WARN] Generation parse error:\n{text[:200]}")
        return []


# ---------------------------------------------------------------------------
# Results logging
# ---------------------------------------------------------------------------

def log_arena_result(entry: dict):
    header = "round\tpitch\tmedian\tmean\tmin\tmax\tstatus\tsubmission_id\n"
    if not os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "w") as f:
            f.write(header)
    pitch_escaped = entry["pitch"].replace("\t", " ")
    with open(RESULTS_FILE, "a") as f:
        f.write(f"{entry['round']}\t{pitch_escaped}\t{entry['median']:.1f}\t"
                f"{entry.get('mean', 0):.1f}\t{entry.get('min', 0):.1f}\t"
                f"{entry.get('max', 0):.1f}\t{entry['status']}\t"
                f"{entry.get('id', '')}\n")


# ---------------------------------------------------------------------------
# Main — meant to be driven by Claude Code with Chrome DevTools access
# ---------------------------------------------------------------------------

def print_instructions():
    print("""
========================================================================
SOLUTION 5: Arena Optimization Loop (Browser-Driven)
========================================================================

This solution must be driven by Claude Code with Chrome DevTools MCP.
It cannot run standalone — it needs browser access for authenticated
submissions to the arena.

To use: Ask Claude Code to run the optimization loop. It will:
1. Navigate Chrome to the arena submit page
2. Submit pitches via JavaScript fetch() (using your browser session)
3. Parse results from the SSE stream
4. Generate mutations via the LLM
5. Repeat, keeping the best pitch

The key functions are importable:
    from solution5_arena import (
        submit_via_browser_js, fetch_submission_js,
        generate_mutations, log_arena_result,
        ARENA_PERSONAS, CANDIDATES_PER_ROUND, MAX_ROUNDS
    )
========================================================================
""")


if __name__ == "__main__":
    print_instructions()
