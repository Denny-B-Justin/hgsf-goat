"""
main.py
-------
Entry point for the PDF → CSV extraction pipeline.

Usage:
    python main.py
    python main.py --docs ./docs --output data.csv
    ANTHROPIC_API_KEY=sk-... python main.py

Environment:
    ANTHROPIC_API_KEY   Required. Your Anthropic API key.
    DOCS_FOLDER         Optional override for the docs folder path.
    OUTPUT_CSV          Optional override for the output CSV path.
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from utils import PDFPipeline
load_dotenv()

def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract structured fields from World Bank project PDFs into a CSV."
    )
    parser.add_argument(
        "--docs",
        type=str,
        default=os.environ.get("DOCS_FOLDER", "docs"),
        help="Path to the folder containing PDF files (default: ./docs)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.environ.get("OUTPUT_CSV", "data.csv"),
        help="Output CSV file path (default: data.csv)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Anthropic API key (overrides ANTHROPIC_API_KEY env var)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("   PDF → CSV Extraction Pipeline")
    print("=" * 60)
    print(f"  Docs folder : {args.docs}")
    print(f"  Output CSV  : {args.output}")
    print(f"  Model       : claude-sonnet-4-20250514")
    print("=" * 60 + "\n")

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY not set.\n"
            "Set it as an environment variable:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-...\n"
            "Or pass it via --api-key flag."
        )
        sys.exit(1)

    pipeline = PDFPipeline(
        docs_folder=args.docs,
        api_key=api_key,
        output_path=args.output,
    )

    df = pipeline.run()

    # Print a preview of the results
    print("\nPreview of extracted data:")
    print("-" * 60)
    preview_cols = ["source_file", "PROJ_DEV_OBJECTIVE_DESC", "LEAD_GP_NAME", "CMT_AMT"]
    print(df[preview_cols].to_string(index=False, max_colwidth=60))
    print("-" * 60)
    print(f"\nFull data saved to: {args.output}")


if __name__ == "__main__":
    main()