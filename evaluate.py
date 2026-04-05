"""
Shared evaluation framework for the pen-selling task.
Defines 15 buyer personas and LLM-based price simulation.

Usage:
    from evaluate import evaluate_pitch, BUYERS
    results = evaluate_pitch("Your 140-char pitch here")
"""

import json
import os
import statistics
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Buyer Personas
# ---------------------------------------------------------------------------

@dataclass
class Buyer:
    name: str
    background: str
    income: str
    relationship_with_pens: str

BUYERS = [
    Buyer("College Student (English Major)", "21-year-old studying literature, takes handwritten notes in every class",
          "$12K/year (part-time barista)", "Uses pens constantly, buys cheap bulk packs"),
    Buyer("Cardiac Surgeon", "48-year-old chief of cardiac surgery at a major hospital",
          "$650K/year", "Signs charts and consent forms daily, owns several luxury pens"),
    Buyer("Cattle Rancher", "55-year-old who runs a 2,000-acre ranch in Montana",
          "$85K/year", "Keeps a pen in shirt pocket for receipts, not picky about brand"),
    Buyer("Corporate Attorney", "38-year-old partner at a top-50 law firm",
          "$450K/year", "Pens are a status symbol in meetings, collects Montblancs"),
    Buyer("Kindergarten Teacher", "32-year-old public school teacher in Ohio",
          "$42K/year", "Goes through pens like water grading papers and making crafts"),
    Buyer("Tech Startup Founder", "29-year-old YC-backed founder in San Francisco",
          "$180K/year (mostly equity)", "Rarely uses pens, lives in digital tools"),
    Buyer("Retired Postal Worker", "67-year-old retiree who does crossword puzzles daily",
          "$38K/year (pension)", "Loyal to specific pen brands, hates cheap ones that skip"),
    Buyer("Freelance Graphic Designer", "34-year-old who sketches concepts by hand before going digital",
          "$72K/year", "Appreciates good design and build quality in tools"),
    Buyer("ER Nurse", "41-year-old night-shift ER nurse",
          "$78K/year", "Pens get lost or borrowed constantly, needs reliable and replaceable"),
    Buyer("High School Principal", "52-year-old running a 1,500-student school",
          "$105K/year", "Signs hundreds of documents per week, values smooth consistent ink"),
    Buyer("Real Estate Agent", "45-year-old top producer in suburban market",
          "$210K/year", "Hands pens to clients at closings, wants impressive but not flashy"),
    Buyer("PhD Astronomy Student", "26-year-old grad student at Caltech",
          "$35K/year (stipend)", "Annotates research papers by hand, budget-conscious"),
    Buyer("Executive Chef", "39-year-old running a Michelin-starred restaurant",
          "$120K/year", "Jots menu changes and orders, pen must survive kitchen conditions"),
    Buyer("Small-Town Pharmacist", "58-year-old who owns an independent pharmacy",
          "$130K/year", "Writes prescription labels and notes, values precision"),
    Buyer("Wedding Planner", "36-year-old running a boutique planning business",
          "$95K/year", "Uses pens in front of clients constantly, aesthetics matter"),
]

# ---------------------------------------------------------------------------
# LLM-based Buyer Simulation
# ---------------------------------------------------------------------------

def _build_buyer_prompt(buyer: Buyer, pitch: str) -> str:
    return f"""You are simulating a buyer in a pen-pricing experiment. You must stay in character.

**Who you are:**
- {buyer.name}
- Background: {buyer.background}
- Annual income: {buyer.income}
- Relationship with pens: {buyer.relationship_with_pens}

**The situation:**
You walk into a store and see a regular pen on the shelf. It's a decent-looking pen — nothing extraordinary, nothing terrible. You can see it for yourself. Then you read the sales pitch on the display card:

"{pitch}"

**Your task:**
Based on your character, income, needs, and how compelling (or not) that pitch is, decide the MAXIMUM price you'd be willing to pay for this pen. Be realistic — this is a real pen on a real shelf, not a luxury collector's item (unless the pitch genuinely convinces you otherwise).

Consider:
- Does the pitch resonate with someone like you?
- Does it make the pen feel more valuable than it looks?
- Would you actually pay this price, or are you just being polite?

Respond with ONLY a JSON object, no other text:
{{"price": <number>, "reasoning": "<one sentence>"}}

The price should be in USD, between $0.50 and $200.00. Be honest to your character."""


def evaluate_pitch(pitch: str, model: str = "claude-sonnet-4-20250514", verbose: bool = True) -> dict:
    """
    Evaluate a sales pitch by simulating 15 buyer responses.
    Returns dict with prices, median, mean, and per-buyer details.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("pip install anthropic  # required for LLM evaluation")

    assert len(pitch) <= 140, f"Pitch must be <=140 chars, got {len(pitch)}"

    client = anthropic.Anthropic(base_url="http://localhost:8317")
    prices = []
    details = []

    for i, buyer in enumerate(BUYERS):
        prompt = _build_buyer_prompt(buyer, pitch)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=150,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Parse JSON response — handle markdown fences or extra text
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            data = json.loads(text)
            price = float(data["price"])
            reasoning = data.get("reasoning", "")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            if verbose:
                print(f"  [{buyer.name}] Parse error: {e}, raw: {text[:100]}")
            price = 2.00  # default fallback
            reasoning = f"parse error: {e}"

        prices.append(price)
        details.append({"buyer": buyer.name, "price": price, "reasoning": reasoning})

        if verbose:
            print(f"  [{i+1:2d}/15] {buyer.name:30s} -> ${price:.2f}  ({reasoning})")

    median = statistics.median(prices)
    mean = statistics.mean(prices)

    if verbose:
        print(f"\n  Median: ${median:.2f}  |  Mean: ${mean:.2f}")
        print(f"  Range: ${min(prices):.2f} - ${max(prices):.2f}")

    return {
        "pitch": pitch,
        "median": median,
        "mean": mean,
        "min": min(prices),
        "max": max(prices),
        "prices": prices,
        "details": details,
    }


def evaluate_pitch_batch(pitches: list[str], **kwargs) -> list[dict]:
    """Evaluate multiple pitches and return results sorted by median (descending)."""
    results = []
    for i, pitch in enumerate(pitches):
        print(f"\n{'='*60}")
        print(f"Pitch {i+1}/{len(pitches)}: \"{pitch}\"")
        print(f"{'='*60}")
        result = evaluate_pitch(pitch, **kwargs)
        results.append(result)
    results.sort(key=lambda r: r["median"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Results logging (autoresearch-style TSV)
# ---------------------------------------------------------------------------

def log_result(result: dict, filepath: str = "results.tsv"):
    """Append a result to the TSV log file."""
    header = "pitch\tmedian\tmean\tmin\tmax\tstatus\n"
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write(header)
    status = "keep" if result.get("keep", True) else "discard"
    pitch_escaped = result["pitch"].replace("\t", " ")
    with open(filepath, "a") as f:
        f.write(f"{pitch_escaped}\t{result['median']:.2f}\t{result['mean']:.2f}\t{result['min']:.2f}\t{result['max']:.2f}\t{status}\n")


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("15 Buyer Personas:")
    for i, b in enumerate(BUYERS, 1):
        print(f"  {i:2d}. {b.name} ({b.income}) — {b.relationship_with_pens}")
    print(f"\nTo evaluate a pitch: evaluate_pitch('your pitch here')")
