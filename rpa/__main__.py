import argparse
import csv
import logging
from pathlib import Path
import sqlite3

from .processing import process_batch


def main():
    parser = argparse.ArgumentParser(description="Process administrative requests from a CSV file")
    parser.add_argument("--input", type=Path, default=Path("data/dados_teste_rpa.csv"))
    parser.add_argument("--db", type=Path, default=Path("output/requests.sqlite"))
    parser.add_argument("--rejections", type=Path, default=Path("output/rejections.csv"))
    parser.add_argument("--report", type=Path, default=Path("output/report.csv"))
    parser.add_argument("--log", type=Path, default=Path("output/execution.log"))
    args = parser.parse_args()

    args.log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=args.log,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logger = logging.getLogger("rpa")
    logger.info("Run start")

    try:
        process_batch(args.input, args.db, args.rejections, args.report, logger)
    except (OSError, ValueError, UnicodeError, csv.Error, sqlite3.Error) as error:
        logger.error("Run error: %s", error)
        logger.info("Run end with error")
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
