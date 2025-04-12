import logging
import sys

# Configure the logging
logging.basicConfig(
    level=logging.INFO,  # Set the default logging level
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # Log to the console
    ],
)


# Create a logger instance for the application
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
