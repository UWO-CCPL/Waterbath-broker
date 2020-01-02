import time
from configparser import ConfigParser

import water_bath_broker
from logger import _configure_logger

if __name__ == '__main__':
    cfg_parser = ConfigParser()
    cfg_parser.read("config.ini")
    _configure_logger(cfg_parser)

    bath_broker = water_bath_broker.WaterBathBroker(cfg_parser)
    while True:
        time.sleep(1)
