"""``python -m truelift.sample``: write the synthetic market (G04/A1, A5, A7)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from truelift.sample.generator import Switches, generate, generate_bundle, parse_seeds


def _switches(args: argparse.Namespace) -> Switches:
    return Switches(unobserved_confounder=args.hidden_confounder, heterogeneity=not args.no_heterogeneity)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m truelift.sample", description="Write the truelift synthetic market and its truth."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_switches(p: argparse.ArgumentParser) -> None:
        p.add_argument("--out", type=Path, required=True, help="output folder")
        p.add_argument(
            "--hidden-confounder",
            action="store_true",
            help="leave the competitor-promotion confounder out of the panel (recorded as hidden)",
        )
        p.add_argument("--no-heterogeneity", action="store_true", help="use one ROI for every row")

    one = sub.add_parser("generate", help="write panel.csv and truth.yaml for one seed")
    one.add_argument("--seed", type=int, required=True)
    add_switches(one)

    many = sub.add_parser("generate-bundle", help="write one seed_NNN folder per seed")
    many.add_argument("--seeds", type=parse_seeds, required=True, help='a range such as "1..20"')
    add_switches(many)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    switches = _switches(args)
    started = time.perf_counter()
    if args.command == "generate":
        truth = generate(args.seed, args.out, switches)
        print(f"seed {args.seed}: true ROI {truth['true_roi']['total']:.4f}, wrote {args.out}")
    else:
        folders = generate_bundle(args.seeds, args.out, switches)
        print(f"wrote {len(folders)} seeds to {args.out} in {time.perf_counter() - started:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
