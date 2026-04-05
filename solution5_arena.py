"""
Solution 5: Anchoring + Iterative Optimization with Real Arena Evaluation

Uses agent-browser CLI for browser automation (no MCP dependency).
Fully self-contained — run it and walk away.

Prerequisites:
  npm install -g agent-browser && agent-browser install
  Set ANTHROPIC_API_KEY and ARENA_SESSION_TOKEN env vars.

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
COOLDOWN = 370           # seconds between submissions (10/hour = 6min, +10s buffer)
MODEL = "gemini-3.1-pro-preview"
ARENA_BASE = "https://www.optimizationarena.com"
RESULTS_FILE = "arena_results.tsv"
KNOWLEDGE_GRAPH = "knowledge_graph.json"

# ---------------------------------------------------------------------------
# Browser helpers (agent-browser CLI)
# ---------------------------------------------------------------------------

def ab_run(args: list[str], timeout: int = 60) -> str:
    """Run an agent-browser command and return stdout."""
    result = subprocess.run(
        ["agent-browser"] + args,
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0 and "error" in result.stderr.lower():
        print(f"  [AB] stderr: {result.stderr[:200]}")
    return result.stdout.strip()


def ab_eval(js: str, timeout: int = 120) -> str:
    """Run JavaScript in the browser page."""
    return ab_run(["eval", js], timeout=timeout)


def setup_browser(session_token: str):
    """Open arena and set auth cookie."""
    print("Setting up browser...")
    ab_run(["open", f"{ARENA_BASE}/persuasion/submit"])
    # Set auth cookie via JS (secure cookie on HTTPS page)
    ab_eval(
        f"document.cookie = '__Secure-authjs.session-token={session_token}; path=/; secure; samesite=lax'"
    )
    ab_run(["reload"])
    time.sleep(2)
    # Verify login
    snap = ab_run(["snapshot", "-i"])
    if "GringamorH" in snap or "Submitting as" in snap:
        print("  Logged in successfully!")
        return True
    elif "Sign in" in snap:
        print("  ERROR: Not logged in. Cookie may be expired.")
        return False
    print(f"  Snapshot: {snap[:200]}")
    return True


def submit_pitch(pitch: str) -> dict | None:
    """Submit a pitch via fetch() in the browser. Returns submission data or None."""
    escaped = pitch.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    js = f"""
(async () => {{
    const resp = await fetch("/api/persuasion/submit-stream", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{description: "{escaped}"}})
    }});
    const text = await resp.text();
    if (resp.status === 429) return {{error: "rate_limit", raw: text.substring(0, 200)}};
    if (resp.status === 401) return {{error: "auth", raw: text.substring(0, 200)}};
    if (!resp.ok) return {{error: "http_" + resp.status, raw: text.substring(0, 200)}};
    const lines = text.split("\\n");
    for (const line of lines) {{
        if (line.startsWith("data: ") && line.includes('"complete"')) {{
            const data = JSON.parse(line.slice(6));
            if (data.stage === "complete" && data.result) return data.result;
        }}
    }}
    return {{error: "no_result", raw: text.substring(0, 300)}};
}})()
"""
    raw = ab_eval(js, timeout=120)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [SUBMIT] Parse error: {raw[:200]}")
        return None

    if data.get("error"):
        err = data["error"]
        if err == "rate_limit":
            print("  RATE LIMITED")
        elif err == "auth":
            print("  AUTH ERROR — cookie expired")
        else:
            print(f"  ERROR: {err} — {data.get('raw', '')[:100]}")
        return None

    sub = data.get("submission", data)
    return sub


def fetch_submission(submission_id: str) -> dict | None:
    """Fetch full submission details including per-persona evaluations."""
    js = f"""
(async () => {{
    const resp = await fetch("/api/persuasion/submissions/{submission_id}");
    return await resp.json();
}})()
"""
    raw = ab_eval(js, timeout=30)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [FETCH] Parse error: {raw[:200]}")
        return None


# ---------------------------------------------------------------------------
# Pitch generation (knowledge-graph-informed)
# ---------------------------------------------------------------------------

def load_knowledge_graph() -> str:
    """Load knowledge graph as context string for mutation prompt."""
    if not os.path.exists(KNOWLEDGE_GRAPH):
        return "(no knowledge graph found)"
    with open(KNOWLEDGE_GRAPH) as f:
        kg = json.load(f)

    # Build compact persona summary from KG
    lines = []
    for tier_name, tier in kg.get("persona_tiers", {}).items():
        lines.append(f"\n{tier['description']}")
        for name, p in tier.get("members", {}).items():
            best = p.get("best_trigger", "?")
            worst = ", ".join(p.get("anti_triggers", [])[:3])
            lines.append(f"  {name}: ${p['range'][0]}-${p['range'][1]} avg=${p['avg']:.0f} | BEST: {best} | AVOID: {worst}")

    lines.append("\nPROVEN STRATEGIES:")
    for name, s in kg.get("strategy_patterns", {}).get("what_works", {}).items():
        lines.append(f"  ✓ {name}: median {s['median_range']} — {s['description'][:80]}")
    for name, s in kg.get("strategy_patterns", {}).get("what_fails", {}).items():
        lines.append(f"  ✗ {name}: median ${s['median']} — {s['why'][:60]}")

    mm = kg.get("median_math", {})
    if mm:
        lines.append(f"\nMEDIAN MATH: {mm.get('to_reach_200', '')}")
        lines.append(f"BLOCKER: {mm.get('blocker', '')}")

    return "\n".join(lines)


def generate_mutations(best_pitch: str, best_median: float, round_num: int,
                       history: list[dict], n: int = CANDIDATES_PER_ROUND) -> list[str]:
    import anthropic
    client = anthropic.Anthropic(base_url="http://localhost:8317")

    kg_context = load_knowledge_graph()

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

Current best (median ${best_median:.1f}):
"{best_pitch}"

History (best first):
{history_text}

KNOWLEDGE GRAPH:
{kg_context}

Round {round_num}/{MAX_ROUNDS}.
{"LATE ROUND: Try radical departures." if is_late_round else ""}

Generate {n} pitches <=140 chars. Each must try a DIFFERENT angle to crack Raj+Jordan+Zara into $200+.
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
        print(f"  [GEN] Parse error:\n{text[:200]}")
        return []


# ---------------------------------------------------------------------------
# Knowledge graph updater
# ---------------------------------------------------------------------------

def update_knowledge_graph(submission: dict, pitch: str):
    """Update the knowledge graph with new submission data."""
    if not os.path.exists(KNOWLEDGE_GRAPH):
        return
    evals = submission.get("evaluations", [])
    if not evals:
        return

    with open(KNOWLEDGE_GRAPH) as f:
        kg = json.load(f)

    # Update per-persona best prices if beaten
    for ev in evals:
        name = ev["name"]
        for tier in kg.get("persona_tiers", {}).values():
            if name in tier.get("members", {}):
                persona = tier["members"][name]
                if ev["price"] > persona["range"][1]:
                    persona["range"][1] = ev["price"]
                    persona["best_trigger"] = f"(auto) from pitch: {pitch[:60]}"
                    persona["best_price"] = ev["price"]
                if ev["price"] < persona["range"][0]:
                    persona["range"][0] = ev["price"]
                # Update avg (rough running average)
                old_n = persona.get("_n", 19)
                persona["avg"] = (persona["avg"] * old_n + ev["price"]) / (old_n + 1)
                persona["_n"] = old_n + 1

    median = submission.get("medianPrice", 0)
    # Track best strategy pattern
    if median > kg["meta"]["best_median"]:
        kg["meta"]["best_median"] = median
        kg["strategy_patterns"]["what_works"]["best_auto"] = {
            "median_range": [median, median],
            "description": pitch,
            "why": f"Auto-discovered. Median ${median}"
        }

    with open(KNOWLEDGE_GRAPH, "w") as f:
        json.dump(kg, f, indent=2)


# ---------------------------------------------------------------------------
# Results logging
# ---------------------------------------------------------------------------

def log_result(entry: dict):
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
# Main optimization loop
# ---------------------------------------------------------------------------

def run():
    session_token = os.environ.get("ARENA_SESSION_TOKEN", "")
    if not session_token:
        print("ERROR: Set ARENA_SESSION_TOKEN env var")
        print("  Get it from browser: DevTools > Application > Cookies > __Secure-authjs.session-token")
        sys.exit(1)

    if not setup_browser(session_token):
        sys.exit(1)

    history = []
    best_pitch = "Hand-forged titanium barrel. Swiss precision mechanics. Writes 50 years without refill. Museum-quality craftsmanship in your pocket."
    best_median = 45.0  # known baseline from previous runs
    best_mean = 180.7
    best_id = None

    print(f"\n{'='*70}")
    print(f"SOLUTION 5: Arena Optimization Loop (agent-browser)")
    print(f"Best known: ${best_median} median | Model: {MODEL}")
    print(f"Budget: {MAX_ROUNDS} rounds x {CANDIDATES_PER_ROUND} = {MAX_ROUNDS * CANDIDATES_PER_ROUND} max submissions")
    print(f"Cooldown: {COOLDOWN}s ({COOLDOWN/60:.0f}min) between submissions")
    print(f"{'='*70}")

    # Skip baseline if we already know it — go straight to mutations
    submission_count = 0

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'='*70}")
        print(f"ROUND {round_num}/{MAX_ROUNDS} | subs: {submission_count} | best: ${best_median:.1f}")
        print(f"Best: \"{best_pitch[:70]}...\"")
        print(f"{'='*70}")

        candidates = generate_mutations(best_pitch, best_median, round_num, history)
        if not candidates:
            print("  No candidates generated, retrying...")
            continue

        for i, pitch in enumerate(candidates):
            if submission_count > 0:
                remaining = COOLDOWN
                print(f"\n  Cooldown {remaining}s...", end="", flush=True)
                while remaining > 0:
                    step = min(60, remaining)
                    time.sleep(step)
                    remaining -= step
                    if remaining > 0:
                        print(f" {remaining}s...", end="", flush=True)
                print(" go!")

            print(f"\n  [{round_num}.{i+1}] \"{pitch}\" ({len(pitch)} chars)")
            result = submit_pitch(pitch)
            submission_count += 1

            if result is None:
                print("  Submission failed. Waiting 5min before retry...")
                time.sleep(300)
                continue

            sub_id = result.get("id", "")
            median = result.get("medianPrice", 0)
            mean = result.get("meanPrice", 0)

            # Fetch full eval details
            evals = []
            if sub_id:
                full = fetch_submission(sub_id)
                if full and full.get("evaluations"):
                    evals = full["evaluations"]
                    # Update KG with new data
                    update_knowledge_graph(full, pitch)

            improved = median > best_median or (median == best_median and mean > best_mean)

            entry = {
                "pitch": pitch, "median": median, "mean": mean,
                "min": result.get("minPrice", 0), "max": result.get("maxPrice", 0),
                "round": round_num, "status": "keep" if improved else "discard",
                "id": sub_id, "evaluations": evals
            }
            history.append(entry)
            log_result(entry)

            # Print results
            print(f"  Result: ${median:.1f} median (${mean:.1f} mean)")
            if evals:
                sorted_evals = sorted(evals, key=lambda e: e["price"])
                low_str = ', '.join(e["name"] + '=$' + str(e["price"]) for e in sorted_evals[:5])
                high_str = ', '.join(e["name"] + '=$' + str(e["price"]) for e in sorted_evals[-3:])
                print(f"  Floor: {low_str}")
                print(f"  Ceil:  {high_str}")

            if improved:
                best_median = median
                best_mean = mean
                best_pitch = pitch
                best_id = sub_id
                print(f"  >>> NEW BEST: ${best_median:.1f} median <<<")
            else:
                print(f"  Discard (${median:.1f} vs best ${best_median:.1f})")

    # --- Final summary ---
    print(f"\n{'='*70}")
    print(f"OPTIMIZATION COMPLETE")
    print(f"{'='*70}")
    print(f"Total submissions: {submission_count}")
    print(f"\nBest pitch ({len(best_pitch)} chars):")
    print(f'  "{best_pitch}"')
    print(f"\nFINAL SCORE: ${best_median:.1f} median")
    if best_id:
        print(f"Submission: {ARENA_BASE}/persuasion/submissions/{best_id}")

    print(f"\n{'='*70}")
    print(f"FULL LOG")
    print(f"{'='*70}")
    print(f"{'Rnd':>3} {'St':>7} {'Med':>6} {'Mean':>6}  Pitch")
    print("-" * 90)
    for h in history:
        marker = "*" if h["status"] == "keep" else " "
        trunc = h["pitch"][:60] + "..." if len(h["pitch"]) > 60 else h["pitch"]
        print(f"{h['round']:3d} {h['status'].upper():>7} ${h['median']:5.1f} ${h.get('mean',0):5.1f} {marker} {trunc}")


if __name__ == "__main__":
    run()
