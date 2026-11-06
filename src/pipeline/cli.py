"""Command line entry point.

    python -m pipeline screen   --profile config/profile.example.json --jobs examples/jobs.json
    python -m pipeline validate --cv examples/cv_sample.txt --master examples/cv_master.txt \
                                --rules config/truth_rules.example.json
    python -m pipeline report   --tracker examples/tracker.sample.csv
"""

from __future__ import annotations

import argparse
import sys

from .models import Job, Profile
from .report import render
from .screening import screen_all
from .tracker import Tracker
from .truth_gate import Rules, validate


def cmd_screen(args: argparse.Namespace) -> int:
    profile = Profile.load(args.profile)
    decisions = screen_all(Job.load_many(args.jobs), profile)
    for decision in decisions:
        print(decision.explain())
    passed = sum(1 for d in decisions if d.verdict == "pass")
    print(f"\n{passed}/{len(decisions)} postings passed the filters")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    with open(args.cv, encoding="utf-8") as fh:
        cv_text = fh.read()
    with open(args.master, encoding="utf-8") as fh:
        master_text = fh.read()
    result = validate(cv_text, master_text, Rules.load(args.rules))
    print(result.render())
    return 0 if result.approved else 1


def cmd_report(args: argparse.Namespace) -> int:
    print(render(Tracker.load(args.tracker)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    screen = sub.add_parser("screen", help="run the hard filters over a job list")
    screen.add_argument("--profile", required=True)
    screen.add_argument("--jobs", required=True)
    screen.set_defaults(func=cmd_screen)

    val = sub.add_parser("validate", help="run the truth and ATS gates over a CV")
    val.add_argument("--cv", required=True)
    val.add_argument("--master", required=True)
    val.add_argument("--rules", required=True)
    val.set_defaults(func=cmd_validate)

    rep = sub.add_parser("report", help="print the funnel from a tracker CSV")
    rep.add_argument("--tracker", required=True)
    rep.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
