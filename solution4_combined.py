"""
Solution 4: Anchoring + Iterative Optimization

Combines Solution 1's strong anchoring seed with Solution 3's autoresearch loop.
Instead of exploring random angles, we start from a proven psychology baseline
and optimize within the premium-anchoring frame, with late-round wildcards.

Usage: uv run solution4_combined.py
"""

import json
import statistics

from evaluate import evaluate_pitch, log_result, BUYERS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ROUNDS = 5
CANDIDATES_PER_ROUND = 4
MODEL = "gemini-3.1-pro-preview"

# The strong seed from Solution 1
SEED_PITCH = "Writes like a $50 pen. Balanced weight, impossibly smooth ink. Once you hold it, cheap pens feel broken. Treat yourself — you've earned it."

assert len(SEED_PITCH) <= 140

# ---------------------------------------------------------------------------
# Mutation generation
# ---------------------------------------------------------------------------

def generate_mutations(best_pitch: str, best_median: float, round_num: int,
                       history: list[dict], n: int = CANDIDATES_PER_ROUND) -> list[str]:
    import anthropic
    client = anthropic.Anthropic(base_url="http://localhost:8317")

    history_lines = []
    for h in sorted(history, key=lambda x: x["median"], reverse=True)[:10]:
        history_lines.append(f'  median ${h["median"]:.2f} | "{h["pitch"]}"')
    history_text = "\n".join(history_lines) if history_lines else "  (none yet)"

    buyer_summary = "\n".join(
        f"  - {b.name} ({b.income}): {b.relationship_with_pens}"
        for b in BUYERS
    )

    is_late_round = round_num >= MAX_ROUNDS - 1
    wildcard_instruction = ""
    if is_late_round:
        wildcard_instruction = f"""
IMPORTANT: This is a late round. Generate {n - 1} anchoring variants as usual,
but make the LAST pitch a wildcard — a completely different persuasion angle
(emotional, scarcity, social proof, humor, etc). This tests if the anchoring
frame has hit its ceiling."""

    prompt = f"""You are optimizing a 140-character sales pitch for a pen on a store shelf.
Score = median willingness to pay across 15 diverse buyers.

**Buyers:**
{buyer_summary}

**Current best** (median ${best_median:.2f}):
"{best_pitch}"

**History** (best first):
{history_text}

**Strategy context:**
The best pitches use PRICE ANCHORING — referencing expensive pens to shift the
buyer's reference frame upward. Stay within this frame for most candidates.

Specific levers to vary:
- Reference price ($30 vs $50 vs $75 vs "luxury")
- Sensory details (smooth ink, balanced weight, grip, click feel)
- Loss aversion phrasing ("cheap pens feel broken" vs "you'll never go back")
- Permission/identity close ("treat yourself" vs "you deserve better" vs "professionals choose")
- Targeting the MEDIAN buyer: middle-income, practical, uses pens regularly
{wildcard_instruction}

Generate exactly {n} new pitches. Each MUST be <=140 characters.
Respond with ONLY a JSON array of strings, no other text."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.8,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Try to extract JSON array even if wrapped in markdown fences or extra text
    import re
    # Look for [...] anywhere in the response
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        pitches = json.loads(text)
        valid = [p for p in pitches if isinstance(p, str) and len(p) <= 140]
        return valid[:n]
    except json.JSONDecodeError:
        print(f"  [WARN] Parse error. Raw response:\n{text[:300]}")
        return []


# ---------------------------------------------------------------------------
# Experiment loop
# ---------------------------------------------------------------------------

def run():
    history = []
    best_pitch = SEED_PITCH
    best_median = 0.0
    best_mean = 0.0

    print("=" * 60)
    print("SOLUTION 4: Anchoring + Iterative Optimization")
    print("=" * 60)

    # --- Round 0: Establish baseline with the seed ---
    print(f"\n--- BASELINE: \"{SEED_PITCH}\" ({len(SEED_PITCH)} chars) ---\n")
    result = evaluate_pitch(SEED_PITCH, model=MODEL)
    best_median = result["median"]
    best_mean = result["mean"]
    history.append({"pitch": SEED_PITCH, "median": best_median, "mean": best_mean,
                    "round": 0, "status": "keep"})
    log_result({**result, "keep": True})
    print(f"\n  BASELINE: ${best_median:.2f} median, ${best_mean:.2f} mean")

    # --- Optimization rounds ---
    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'='*60}")
        print(f"ROUND {round_num}/{MAX_ROUNDS} | best so far: \"{best_pitch}\" (${best_median:.2f})")
        print(f"{'='*60}")

        candidates = generate_mutations(best_pitch, best_median, round_num, history)
        if not candidates:
            print("  No valid candidates generated, skipping round")
            continue

        for i, pitch in enumerate(candidates):
            print(f"\n--- [{round_num}.{i+1}] \"{pitch}\" ({len(pitch)} chars) ---\n")
            result = evaluate_pitch(pitch, model=MODEL)
            entry = {"pitch": pitch, "median": result["median"], "mean": result["mean"],
                     "round": round_num, "status": "pending"}

            improved = False
            if result["median"] > best_median:
                improved = True
            elif result["median"] == best_median and result["mean"] > best_mean:
                improved = True  # tie-break on mean

            if improved:
                best_median = result["median"]
                best_mean = result["mean"]
                best_pitch = pitch
                entry["status"] = "keep"
                print(f"  -> NEW BEST: ${best_median:.2f} median, ${best_mean:.2f} mean")
            else:
                entry["status"] = "discard"
                print(f"  -> Discard (${result['median']:.2f} vs best ${best_median:.2f})")

            history.append(entry)
            log_result({**result, "keep": improved})

    # --- Final summary ---
    print(f"\n{'='*60}")
    print(f"OPTIMIZATION COMPLETE — {len(history)} pitches evaluated")
    print(f"{'='*60}")
    print(f"\nBest pitch ({len(best_pitch)} chars):")
    print(f'  "{best_pitch}"')
    print(f"\nFINAL SCORE: ${best_median:.2f} median, ${best_mean:.2f} mean")

    print(f"\n{'='*60}")
    print(f"EXPERIMENT LOG")
    print(f"{'='*60}")
    print(f"{'Rnd':>3} {'Status':>8} {'Median':>8} {'Mean':>8}  Pitch")
    print("-" * 90)
    for h in history:
        marker = "*" if h["status"] == "keep" else " "
        trunc = h["pitch"][:65] + "..." if len(h["pitch"]) > 65 else h["pitch"]
        print(f"{h['round']:3d} {h['status'].upper():>8} ${h['median']:6.2f} ${h['mean']:6.2f} {marker} {trunc}")

    return best_pitch, best_median


if __name__ == "__main__":
    run()
