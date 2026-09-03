import logging


def configure_logging() -> None:
    """Basic structured console logging. Extend when observability needs grow."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
