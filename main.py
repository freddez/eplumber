import logging
from eplumber import Eplumber

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.DEBUG)
    e = Eplumber()
    e.get_config()


if __name__ == "__main__":
    main()
