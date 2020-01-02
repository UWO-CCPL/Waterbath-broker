import time
from configparser import ConfigParser

from logger import _configure_logger

if __name__ == '__main__':
    cfg_parser = ConfigParser()
    cfg_parser.read("config.ini")
    _configure_logger(cfg_parser)

    broker = FP50Broker(cfg_parser)
    broker.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        broker.stop()
        broker.join()
