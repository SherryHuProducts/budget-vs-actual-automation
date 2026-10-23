import argparse
from .pipeline import seed, run


def main():
    parser = argparse.ArgumentParser(description="Budget vs actual automation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="Create deterministic sample data")
    process = commands.add_parser("run", help="Generate reports")
    process.add_argument("--through", default="2026-09", help="Close month YYYY-MM")
    args = parser.parse_args()
    if args.command == "seed":
        print(f"Created {seed()}")
    else:
        for key, value in run(args.through).items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
