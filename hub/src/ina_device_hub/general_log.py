import os
from logging import DEBUG, Formatter, Logger, StreamHandler, getLogger
from logging.handlers import RotatingFileHandler

from ina_device_hub.setting import setting

log_dir = os.path.join(setting().get_work_dir(), "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_size = 1024 * 1024 * 10
log_num = 100


class AutoFlushStreamHandler(StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


def get_rotate_file_logger(name: str, log_file: str) -> Logger:
    logger = getLogger(name)
    logger.setLevel(DEBUG)
    formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # setup file handler
    rotate_handler = RotatingFileHandler(f"{log_dir}/{log_file}", maxBytes=log_size, backupCount=log_num)
    rotate_handler.setLevel(DEBUG)
    rotate_handler.setFormatter(formatter)
    logger.addHandler(rotate_handler)

    # setup stdout handler
    stdout_handler = AutoFlushStreamHandler()
    stdout_handler.setLevel(DEBUG)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    return logger


logger = get_rotate_file_logger("general", "general.log")
