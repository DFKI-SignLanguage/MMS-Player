import logging
import datetime
import tempfile


_timestamp_str = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

# Create a temporary file path
logging_filepath = tempfile.gettempdir() + f"/mms_run_log_{_timestamp_str}.txt"
# log_file_path = f"mms_run_log_{timestamp_str}.txt"

logging.basicConfig(
    filename=logging_filepath,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)

print(f"Logging to '{logging_filepath}'.")


def enable_log_to_stdout():
    # Create a console handler to print logs to the console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)
