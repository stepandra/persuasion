"""
Solution 2: Universal Utility & Emotional Resonance

STRATEGY:
Instead of anchoring to price, this approach anchors to MEANING.
Every person — regardless of income — values the things they write.
By connecting the pen to what matters in the buyer's life, we make
the pen feel like more than a commodity.

Key psychological levers:
- Identity framing: "Your words matter" — validates every buyer
- Scarcity of quality: "pen that keeps up" implies most don't
- Emotional connection: Ties the pen to their life's work, not just writing
- Implicit quality: "Never skips, never smears" = concrete reliability proof

This approach intentionally avoids price comparisons. Instead of "worth $X",
it makes the buyer ask "what are my words worth?" — an unanswerable question
that biases upward.

Usage: uv run solution2_universal.py
"""

from evaluate import evaluate_pitch, log_result

# ---------------------------------------------------------------------------
# The Pitch (140 chars max)
# ---------------------------------------------------------------------------

PITCH = "Your words matter. Your pen should too. Never skips, never smears, never lets you down. A pen that keeps up with everything you need to say."

assert len(PITCH) <= 140, f"Pitch is {len(PITCH)} chars, must be <=140"

# ---------------------------------------------------------------------------
# Strategy breakdown
# ---------------------------------------------------------------------------

STRATEGY = """
APPROACH: Universal Utility & Emotional Resonance

Why this works across all 15 buyers:
- "Your words matter": This is true for EVERYONE — the surgeon signing
  consent forms, the student taking notes, the rancher writing receipts,
  the attorney drafting contracts. It validates their work.
- "Your pen should too": Logical bridge. If words matter, the tool matters.
  This is the moment the buyer stops thinking "it's just a pen."
- "Never skips, never smears, never lets you down": Triple proof of
  reliability. The ER nurse who loses pens needs reliability. The retiree
  who hates skippy pens needs reliability. The principal signing 100
  documents needs reliability. This is the universal pain point.
- "A pen that keeps up with everything you need to say": Aspirational
  close. Implies the buyer has important things to say (flattery) and
  this pen won't be the bottleneck.

Expected effect by buyer segment:
  WRITERS (student, teacher, principal): Strong resonance — they write a LOT
  SIGNERS (surgeon, attorney, RE agent): "Your words matter" = their signature
  PRACTICAL (rancher, nurse, chef): "Never lets you down" = reliability
  CREATIVE (designer, planner): "Keeps up with everything" = flow state
"""

# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("SOLUTION 2: Universal Utility & Emotional Resonance")
    print("=" * 60)
    print(f"\nPitch ({len(PITCH)} chars):")
    print(f'  "{PITCH}"')
    print(f"\n{STRATEGY}")
    print("Evaluating with 15 buyer personas...\n")

    result = evaluate_pitch(PITCH)
    result["approach"] = "universal"
    log_result(result)

    print(f"\n{'='*60}")
    print(f"FINAL SCORE (median): ${result['median']:.2f}")
    print(f"{'='*60}")
