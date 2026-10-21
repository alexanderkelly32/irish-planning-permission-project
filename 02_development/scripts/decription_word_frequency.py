# word_frequency_from_column_d.py
# Reads a CSV, extracts descriptions from column D (4th column), and ranks all words by frequency.

import re
from collections import Counter
from pathlib import Path

import pandas as pd

# -----------------------
# CONFIG (edit these)
# -----------------------
INPUT_CSV = "greater_than_15_units_data.csv"          # <-- put your CSV filename/path here
OUTPUT_CSV = "word_analysis.csv"   # <-- output file
COLUMN_INDEX = 3                     # Column D = 0:A, 1:B, 2:C, 3:D
LOWERCASE = True
KEEP_NUMBERS = True
# -----------------------

def tokenize(text: str) -> list[str]:
    if LOWERCASE:
        text = text.lower()

    # Token pattern:
    # - words with letters (and optional apostrophes) e.g., "don’t" -> "don", "t" unless you normalize unicode apostrophes
    # - numbers if KEEP_NUMBERS=True
    if KEEP_NUMBERS:
        pattern = r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?"
    else:
        pattern = r"[a-z]+(?:'[a-z]+)?"

    return re.findall(pattern, text)

def main():
    in_path = Path(INPUT_CSV)
    if not in_path.exists():
        raise FileNotFoundError(f"Cannot find input CSV: {in_path.resolve()}")

    # Read CSV
    df = pd.read_csv(in_path, dtype=str, keep_default_na=False)

    if df.shape[1] <= COLUMN_INDEX:
        raise ValueError(f"CSV has {df.shape[1]} columns, but COLUMN_INDEX={COLUMN_INDEX} was requested.")

    # Extract column D (by index)
    desc = df.iloc[:, COLUMN_INDEX].astype(str)

    # Tokenize + count
    counter = Counter()
    for s in desc:
        if not s.strip():
            continue
        counter.update(tokenize(s))

    # Build output table
    out_df = pd.DataFrame(counter.most_common(), columns=["word", "count"])

    # Save
    out_df.to_csv(OUTPUT_CSV, index=False)

    # Print a quick preview
    print(f"Saved: {OUTPUT_CSV} (rows={len(out_df)})")
    print("\nTop 50 words:")
    print(out_df.head(50).to_string(index=False))

if __name__ == "__main__":
    main()
