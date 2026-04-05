"""
Solution 1: Premium Anchoring & Status Signaling

STRATEGY:
Price anchoring is the most robust persuasion technique across diverse demographics.
By framing the pen's value relative to an expensive reference point, every buyer
mentally adjusts upward from their default "it's just a pen" baseline.

Key psychological levers:
- Anchoring: Mention what premium pens cost to shift the reference frame
- Loss aversion: Imply they're getting a deal / missing out
- Identity signaling: Make owning this pen say something about the buyer
- Sensory language: "smooth" and "balanced" trigger tactile imagination

The pitch targets the MEDIAN buyer, not the extremes. We don't need the surgeon
to pay $200 — we need the teacher, nurse, and rancher to pay $15+ instead of $3.

Usage: uv run solution1_anchoring.py
"""

from evaluate import evaluate_pitch, log_result

# ---------------------------------------------------------------------------
# The Pitch (140 chars max)
# ---------------------------------------------------------------------------

PITCH = "Writes like a $50 pen. Balanced weight, impossibly smooth ink. Once you hold it, cheap pens feel broken. Treat yourself — you've earned it."

assert len(PITCH) <= 140, f"Pitch is {len(PITCH)} chars, must be <=140"

# ---------------------------------------------------------------------------
# Strategy breakdown
# ---------------------------------------------------------------------------

STRATEGY = """
APPROACH: Premium Anchoring & Status Signaling

Why this works across all 15 buyers:
- "$50 pen" anchor: Sets the mental reference price HIGH. Even skeptics now
  think "well, if it writes like a $50 pen, $15 seems reasonable."
- "Balanced weight, impossibly smooth": Sensory details that every pen user
  values, regardless of profession. The surgeon and the student both want
  smooth ink.
- "Cheap pens feel broken": Loss aversion — once framed this way, buying a
  $2 pen feels like losing quality. This shifts the floor price upward.
- "Treat yourself — you've earned it": Permission to spend. The budget-
  conscious buyers (student, teacher, retiree) are most price-sensitive,
  but this phrase gives them emotional permission to splurge a little.

Expected effect by buyer segment:
  HIGH income (surgeon, attorney, RE agent): $25-50 — they respect quality
  MID income (principal, chef, pharmacist): $15-25 — the anchor works
  LOW income (student, teacher, retiree): $8-15 — "treat yourself" helps
"""

# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("SOLUTION 1: Premium Anchoring & Status Signaling")
    print("=" * 60)
    print(f"\nPitch ({len(PITCH)} chars):")
    print(f'  "{PITCH}"')
    print(f"\n{STRATEGY}")
    print("Evaluating with 15 buyer personas...\n")

    result = evaluate_pitch(PITCH)
    result["approach"] = "anchoring"
    log_result(result)

    print(f"\n{'='*60}")
    print(f"FINAL SCORE (median): ${result['median']:.2f}")
    print(f"{'='*60}")
