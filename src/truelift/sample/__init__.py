"""The public synthetic market with known truth (design D14; contracts C14, C4, C3).

``python -m truelift.sample generate --seed 1 --out DIR`` writes one panel and its truth.yaml;
``generate-bundle --seeds 1..20 --out DIR`` writes the coverage set. Seed 1 is committed under
``data/sample/``.
"""

from truelift.sample.generator import Switches, generate, generate_bundle, parse_seeds, simulate

__all__ = ["Switches", "generate", "generate_bundle", "parse_seeds", "simulate"]
