"""Test priority and end dates in suggestions."""
import sys
sys.path.insert(0, "src")

from polytrade.services.analyzer.analysis import run_analysis

print("Running analyzer...")
suggestions = run_analysis(max_suggestions=3)

print(f"\n{'='*80}")
print("SUGGESTIONS WITH END DATES AND PRIORITY:")
print('='*80)

for i, s in enumerate(suggestions, 1):
    title = s.get("title", "N/A")
    end_date = s.get("endDate", "N/A")
    priority = s.get("priority", "N/A")
    
    priority_label = {
        1: "🔴 URGENT (ends in 24h)",
        2: "🟡 Later (>24h)",
        3: "⚪ No date"
    }.get(priority, "Unknown")
    
    print(f"\n{i}. {title[:70]}")
    print(f"   End Date: {end_date}")
    print(f"   Priority: {priority_label}")

print(f"\n{'='*80}\n")

