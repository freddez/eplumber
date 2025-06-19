import logging
import argparse
from eplumber import Eplumber

logger = logging.getLogger(__name__)


def get_log_level(level_str):
    """Convert string log level to logging constant"""
    levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    return levels.get(level_str.lower(), logging.INFO)


def main():
    parser = argparse.ArgumentParser(description="Eplumber IoT Automation System")
    parser.add_argument(
        "--loglevel",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Set the logging level (default: info)",
    )

    args = parser.parse_args()
    log_level = get_log_level(args.loglevel)

    logging.basicConfig(level=log_level)
    e = Eplumber(log_level=args.loglevel)
    e.get_config()


if __name__ == "__main__":
    main()
