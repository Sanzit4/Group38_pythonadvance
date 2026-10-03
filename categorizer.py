from dotenv import load_dotenv
load_dotenv()

import os
import requests
import statistics

HF_TOKEN = os.environ.get("HF_TOKEN")
API_URL = "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

CATEGORIES = [
    "Travel",
    "Meals & Entertainment",
    "Office Supplies",
    "Software & Subscriptions",
    "Utilities",
    "Marketing",
    "Professional Services",
    "Equipment",
    "Training & Education",
    "Other",
]


def categorize(description: str) -> str:
    """
    Categorizes a single expense description using Hugging Face's zero-shot classifier.
    Returns just the category name as a plain string, matching what app.py expects.
    """
    payload = {
        "inputs": description,
        "parameters": {"candidate_labels": CATEGORIES},
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        top_label = result[0]["label"]
        return top_label
    except Exception as e:
        print(f"Categorization error: {e}")
        return "Other"  # safe fallback so the app doesn't crash on API hiccups


def is_unusual_expense(amount: float, past_amounts: list, flat_threshold: float = 50000) -> tuple[bool, str]:
    """
    Flags an expense as unusual based on the employee's own spending history,
    plus a configurable flat threshold set by the admin.
    Returns (flagged: bool, reason: str), matching what app.py expects.
    """
    if past_amounts:
        avg = statistics.mean(past_amounts)
        stdev = statistics.stdev(past_amounts) if len(past_amounts) > 1 else 0

        # Flag if this expense is far above the person's typical spending
        if amount > avg + (2 * stdev) and amount > avg * 1.5:
            return True, f"Amount (₦{amount:,.2f}) is significantly higher than your average expense (₦{avg:,.2f})."

    # Flag flat outliers regardless of history — threshold is admin-configurable
    if amount > flat_threshold:
        return True, f"Amount (₦{amount:,.2f}) exceeds the organization's review threshold (₦{flat_threshold:,.2f})."

    return False, ""

# --- Standalone test ---
if __name__ == "__main__":
    test_cases = [
        ("Flight to client site", 412.50, [120, 95, 430, 88]),
        ("Monthly team subscription", 89.00, [80, 85, 90]),
        ("Printer paper and pens", 34.20, [30, 45, 20]),
    ]

    for description, amount, history in test_cases:
        category = categorize(description)
        flagged, reason = is_unusual_expense(amount, history)
        print(f"{description:30} -> {category} | Unusual: {flagged} {reason}")