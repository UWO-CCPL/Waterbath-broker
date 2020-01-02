import configparser
import logging

import rx
from influxdb import InfluxDBClient
import paho.mqtt.client as mqtt
from rx import operators
from rx.scheduler import NewThreadScheduler

from fp50 import FP50Control

logger = logging.getLogger("water_bath")


class WaterBathBroker:
    def __init__(self, config: configparser.ConfigParser):
        self.config = config

        self.influxdb = InfluxDBClient(
            self.config.get("influxdb", "host"),
            self.config.getint("influxdb", "port"),
            self.config.get("influxdb", "username"),
            self.config.get("influxdb", "password"),
            self.config.get("influxdb", "database"),
        )
        logger.info("InfluxDB client connected")

        self.mqtt = mqtt.Client(self.config.get("mqtt", "id"))
        self.mqtt.connect(
            self.config.get("mqtt", "host"),
            self.config.getint("mqtt", "port"),
        )
        self.configure_mqtt_topics()
        logger.info("MQTT client connected")

        self.control = FP50Control(
            self.config.get("fp50", "serial"),
            self.config.getint("fp50", "baud"),
            self.config.getfloat("fp50", "command_interval")
        )
        self.control.startup()
        logger.info("FP50 control connected")

        self.configure_timed_read()

    def configure_mqtt_topics(self):
        if not self.mqtt.is_connected():
            raise RuntimeError("MQTT is not connected!")

        topic = "fp50/+/setpoint"
        self.mqtt.subscribe(topic)

        self.mqtt.message_callback_add(topic, self.temperature_setpoint_changed)

    def temperature_setpoint_changed(self, data):
        try:
            data = float(data)
        except ValueError:
            logger.error(f"Failed to parse {data} into float")
            return
        self.control.set_temperature(data)

    def configure_timed_read(self):
        power_upload_interval = self.config.getfloat("influxdb", "power_upload_interval")
        internal_temperature_upload_interval = self.config.getfloat("influxdb", "internal_temperature_upload_interval")

        if power_upload_interval > 0:
            # enabled
            rx.interval(power_upload_interval, scheduler=NewThreadScheduler()).pipe(
                operators.flat_map(lambda x: self.control.get_power())
            ).subscribe(self.upload_power)
        if internal_temperature_upload_interval > 0:
            # enabled
            rx.interval(internal_temperature_upload_interval, scheduler=NewThreadScheduler()).pipe(
                operators.flat_map(lambda x: self.control.get_internal_temperature())
            ).subscribe(self.upload_internal_temperature)

    def upload_power(self, power):
        json_body = [{
            "measurement": "water_bath",
            "tags": {
                "device": self.config.get("tags", "device"),
                "location": self.config.get("tags", "location"),
            },
            "fields": {
                "power": power
            }
        }]

        self.influxdb.write_points(json_body)
        logger.info(f"Power={power} uploaded to InfluxDB")

    def upload_internal_temperature(self, internal_temperature):
        json_body = [{
            "measurement": "water_bath",
            "tags": {
                "device": self.config.get("tags", "device"),
                "location": self.config.get("tags", "location"),
            },
            "fields": {
                "internal_temperature": internal_temperature
            }
        }]

        self.influxdb.write_points(json_body)
        logger.info(f"Internal temperature={internal_temperature} uploaded to InfluxDB")
