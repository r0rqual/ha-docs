#!/usr/bin/env python3
"""
Parse eBird bar chart TSV to JSON for rare bird alerts.
Uses official eBird taxonomy for accurate species code mapping.

Usage:
  python parse_ebird_barchart.py ebird_US-WI-025_barchart.txt eBird_taxonomy_v2025.csv dane_county_frequencies.json

Downloads needed:
  - Bar chart: https://ebird.org/barchart?r=US-WI-025 → "Download Histogram Data" (requires login)
  - Taxonomy: https://www.birds.cornell.edu/clementschecklist/wp-content/uploads/2025/10/eBird_taxonomy_v2025.csv
"""
import csv
import json
import sys


def load_taxonomy(taxonomy_file):
    """Load eBird taxonomy CSV, return dict of common_name -> species_code."""
    name_to_code = {}
    with open(taxonomy_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            common_name = row['PRIMARY_COM_NAME'].strip()
            species_code = row['SPECIES_CODE'].strip().lower()
            name_to_code[common_name] = species_code
            # Also store without parenthetical subspecies info
            base_name = common_name.split(' (')[0].strip()
            if base_name not in name_to_code:
                name_to_code[base_name] = species_code
    return name_to_code


def parse_barchart(barchart_file, name_to_code):
    """Parse eBird bar chart TSV, return dict of species_code -> [48 frequencies]."""
    frequencies = {}
    unmatched = []

    with open(barchart_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('Sample Size'):
                continue
            parts = line.split('\t')
            if len(parts) < 49:
                continue
            species_name = parts[0].strip()
            # Skip header row
            if any(x in species_name.lower() for x in ['january', 'february', 'march']):
                continue
            try:
                week_freqs = [float(parts[i].strip() or 0) for i in range(1, 49)]
                # Look up species code from taxonomy
                code = name_to_code.get(species_name)
                if code:
                    frequencies[code] = week_freqs
                else:
                    unmatched.append(species_name)
            except (ValueError, IndexError):
                continue

    if unmatched:
        print(f"Warning: {len(unmatched)} species not found in taxonomy:")
        for name in unmatched[:10]:
            print(f"  - {name}")
        if len(unmatched) > 10:
            print(f"  ... and {len(unmatched) - 10} more")

    return frequencies


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python parse_ebird_barchart.py <barchart.txt> <taxonomy.csv> <output.json>")
        print()
        print("Arguments:")
        print("  barchart.txt  - Downloaded from https://ebird.org/barchart?r=US-WI-025")
        print("  taxonomy.csv  - Downloaded from https://www.birds.cornell.edu/clementschecklist/download/")
        print("  output.json   - Output file (copy to /Volumes/config/www/)")
        sys.exit(1)

    barchart_file = sys.argv[1]
    taxonomy_file = sys.argv[2]
    output_file = sys.argv[3]

    print(f"Loading taxonomy from {taxonomy_file}...")
    name_to_code = load_taxonomy(taxonomy_file)
    print(f"Loaded {len(name_to_code)} species names")

    print(f"Parsing bar chart from {barchart_file}...")
    frequencies = parse_barchart(barchart_file, name_to_code)
    print(f"Found {len(frequencies)} species with frequency data")

    print(f"Writing {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(frequencies, f)

    print("Done!")
    print(f"\nNext step: Copy {output_file} to /Volumes/config/www/dane_county_frequencies.json")
