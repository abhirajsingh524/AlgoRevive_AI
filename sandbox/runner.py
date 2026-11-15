import argparse
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="AlgoRevive Sandbox Runner")
    parser.add_argument("--mode", choices=["profile", "validate", "benchmark"], required=True)
    parser.add_argument("--spec", default="/work/job.json", help="Path to job spec file")
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"AlgoRevive sandbox runner started in mode: {args.mode}")
    # Full profiling implementation in Task 5
    sys.exit(0)


if __name__ == "__main__":
    main()
