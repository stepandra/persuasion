"""
Solution 3: Autoresearch-Style Iterative Optimization

STRATEGY:
Instead of hand-crafting a single pitch, use the autoresearch experiment loop:
generate candidate pitches, evaluate each one, keep the best, mutate, repeat.
This is the "let the LLM be its own researcher" approach.

The loop:
1. Generate N candidate pitches using different persuasion angles
2. Evaluate each against all 15 buyers
3. Keep the best performer (highest median)
4. Use the best as a seed to generate mutations
5. Repeat until convergence or budget exhaustion

This mirrors autoresearch/program.md: modify -> run -> measure -> keep/discard.

Usage: uv run solution3_iterative.py
"""

import json
import os
import statistics
import time

from evaluate import evaluate_pitch, evaluate_pitch_batch, log_result, BUYERS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ROUNDS = 5             # number of optimization rounds
CANDIDATES_PER_ROUND = 4   # pitches generated per round
MODEL = "claude-sonnet-4-20250514"  # model for both generation and evaluation

# ---------------------------------------------------------------------------
# Seed pitches (diverse starting points)
# ---------------------------------------------------------------------------

SEED_PITCHES = [
    # Anchoring angle
    "Writes like a $50 pen at a fraction of the price. Smooth ink, perfect weight. Your hand will thank you.",
    # Emotional angle
    "Every signature tells a story. Every note captures a moment. This pen makes sure none of them are lost.",
    # Practical angle
    "No skipping. No smearing. No excuses. Just a pen that works every single time you pick it up. Try it once.",
    # Scarcity/quality angle
    "Most pens are forgettable. This one isn't. Premium ink, engineered grip, built to outlast the cheap ones.",
]

# Verify all seeds fit
for p in SEED_PITCHES:
    assert len(p) <= 140, f"Seed pitch too long ({len(p)} chars): {p}"

# ---------------------------------------------------------------------------
# Pitch generation via LLM
# ---------------------------------------------------------------------------

def generate_mutations(best_pitch: str, best_median: float, round_num: int,
                       history: list[dict], n: int = CANDIDATES_PER_ROUND) -> list[str]:
    """
    Generate n new pitch candidates by mutating the current best.
    Uses the evaluation history to avoid repeating failed strategies.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("pip install anthropic")

    client = anthropic.Anthropic(base_url="http://localhost:8317")

    # Build history context
    history_lines = []
    for h in sorted(history, key=lambda x: x["median"], reverse=True)[:10]:
        history_lines.append(f'  "${h["pitch"]}" -> median ${h["median"]:.2f}')
    history_text = "\n".join(history_lines) if history_lines else "  (no history yet)"

    buyer_summary = "\n".join(
        f"  - {b.name} ({b.income}): {b.relationship_with_pens}"
        for b in BUYERS
    )

    prompt = f"""You are optimizing a 140-character sales pitch for a pen on a store shelf.

**Buyers** (15 diverse personas, score = median willingness to pay):
{buyer_summary}

**Current best pitch** (median ${best_median:.2f}):
"{best_pitch}"

**History** (best to worst):
{history_text}

**Round {round_num}/{MAX_ROUNDS}** — generate exactly {n} new pitch candidates.

Guidelines:
- Each must be <=140 characters
- Each should try a DIFFERENT angle or tweak from the current best
- Study the history: what worked? What didn't? Why?
- The median buyer is middle-income, practical, uses pens regularly
- Avoid being too clever or abstract — the pitch is on a shelf display card
- Consider: anchoring, social proof, sensory language, loss aversion, identity

Respond with ONLY a JSON array of {n} strings, no other text:
["{n} pitch candidates here"]"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.8,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    import re
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        pitches = json.loads(text)
        pitches = [p for p in pitches if isinstance(p, str) and len(p) <= 140]
        return pitches[:n]
    except json.JSONDecodeError:
        print(f"  [WARN] Failed to parse LLM response:\n{text[:300]}")
        return SEED_PITCHES[:n]


# ---------------------------------------------------------------------------
# The Experiment Loop (mirrors autoresearch)
# ---------------------------------------------------------------------------

def run_optimization():
    """
    Autoresearch-style optimization loop:
    1. Evaluate seed pitches
    2. Keep the best
    3. Generate mutations from the best
    4. Evaluate mutations
    5. Keep or discard
    6. Repeat
    """
    history = []
    best_pitch = None
    best_median = 0.0

    print("=" * 60)
    print("SOLUTION 3: Iterative Optimization (Autoresearch-Style)")
    print("=" * 60)

    # --- Round 0: Evaluate seed pitches ---
    print(f"\n{'='*60}")
    print(f"ROUND 0: Evaluating {len(SEED_PITCHES)} seed pitches")
    print(f"{'='*60}")

    for i, pitch in enumerate(SEED_PITCHES):
        print(f"\n--- Seed {i+1}/{len(SEED_PITCHES)}: \"{pitch}\" ({len(pitch)} chars) ---")
        result = evaluate_pitch(pitch, model=MODEL)
        entry = {"pitch": pitch, "median": result["median"], "mean": result["mean"],
                 "round": 0, "status": "pending"}
        history.append(entry)

        if result["median"] > best_median:
            best_median = result["median"]
            best_pitch = pitch
            entry["status"] = "keep"
            print(f"  -> NEW BEST: ${best_median:.2f}")
        else:
            entry["status"] = "discard"
            print(f"  -> Below best (${best_median:.2f}), discarding")

    print(f"\n*** After seeds: best = \"{best_pitch}\" (${best_median:.2f}) ***")

    # --- Rounds 1..N: Generate mutations and evaluate ---
    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'='*60}")
        print(f"ROUND {round_num}/{MAX_ROUNDS}: Generating mutations from best")
        print(f"{'='*60}")
        print(f"Current best: \"{best_pitch}\" (${best_median:.2f})")

        candidates = generate_mutations(best_pitch, best_median, round_num, history)
        print(f"Generated {len(candidates)} candidates")

        for i, pitch in enumerate(candidates):
            print(f"\n--- Candidate {i+1}/{len(candidates)}: \"{pitch}\" ({len(pitch)} chars) ---")
            result = evaluate_pitch(pitch, model=MODEL)
            entry = {"pitch": pitch, "median": result["median"], "mean": result["mean"],
                     "round": round_num, "status": "pending"}
            history.append(entry)

            if result["median"] > best_median:
                best_median = result["median"]
                best_pitch = pitch
                entry["status"] = "keep"
                print(f"  -> NEW BEST: ${best_median:.2f}")
                log_result({"pitch": pitch, "median": best_median, "mean": result["mean"],
                           "min": result["min"], "max": result["max"], "keep": True})
            elif result["median"] == best_median and result["mean"] > history[-1].get("mean", 0):
                # Tie-break on mean
                best_pitch = pitch
                entry["status"] = "keep"
                print(f"  -> TIE on median, better mean. Keeping.")
                log_result({"pitch": pitch, "median": best_median, "mean": result["mean"],
                           "min": result["min"], "max": result["max"], "keep": True})
            else:
                entry["status"] = "discard"
                print(f"  -> Below best (${best_median:.2f}), discarding")
                log_result({"pitch": pitch, "median": result["median"], "mean": result["mean"],
                           "min": result["min"], "max": result["max"], "keep": False})

        print(f"\n*** After round {round_num}: best = \"{best_pitch}\" (${best_median:.2f}) ***")

    # --- Final summary ---
    print(f"\n{'='*60}")
    print(f"OPTIMIZATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total pitches evaluated: {len(history)}")
    print(f"Rounds: {MAX_ROUNDS}")
    print(f"\nBest pitch ({len(best_pitch)} chars):")
    print(f'  "{best_pitch}"')
    print(f"\nFINAL SCORE (median): ${best_median:.2f}")

    # Show full history
    print(f"\n{'='*60}")
    print(f"EXPERIMENT LOG (autoresearch-style)")
    print(f"{'='*60}")
    print(f"{'Rnd':>3} {'Status':>8} {'Median':>8} {'Mean':>8}  Pitch")
    print("-" * 80)
    for h in history:
        status = h["status"].upper()
        marker = "*" if status == "KEEP" else " "
        print(f"{h['round']:3d} {status:>8} ${h['median']:6.2f} ${h['mean']:6.2f} {marker} {h['pitch'][:60]}...")

    return best_pitch, best_median


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    best_pitch, best_median = run_optimization()
