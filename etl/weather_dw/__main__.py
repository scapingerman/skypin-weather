import logging
import sys

from weather_dw.logging_conf import setup_logging
from weather_dw.pipeline import run_pipeline

if __name__ == "__main__":
    setup_logging()
    log = logging.getLogger("weather_dw")
    try:
        run_id = run_pipeline()
    except Exception:
        log.exception("ETL failed")
        sys.exit(1)
    log.info("ETL finished successfully run_id=%s", run_id)
    sys.exit(0)
