import configparser
import logging

import rx
from influxdb import InfluxDBClient
import paho.mqtt.client as mqtt
from rx import operators
from rx.scheduler import NewThreadScheduler

from fp50 import FP50Control
from logger import error_handler

logger = logging.getLogger("water_bath")


class WaterBathBroker:
    mqtt: mqtt.Client

    def __init__(self, config: configparser.ConfigParser):
        self.config = config

        self.control = FP50Control(
            self.config.get("fp50", "serial"),
            self.config.getint("fp50", "baud"),
            self.config.getfloat("fp50", "command_interval")
        )
        self.control.startup()
        logger.info("FP50 control connected")

        if self.config.getboolean("influxdb", "enabled"):
            self.influxdb = InfluxDBClient(
                self.config.get("influxdb", "host"),
                self.config.getint("influxdb", "port"),
                self.config.get("influxdb", "username"),
                self.config.get("influxdb", "password"),
                self.config.get("influxdb", "database"),
            )
            logger.info("InfluxDB client connected")
        else:
            self.influxdb = None

        if self.config.getboolean("mqtt", "enabled"):
            self.base_topic = self.config.get("mqtt", "topic")
            self.mqtt = mqtt.Client(self.config.get("mqtt", "id"), protocol=mqtt.MQTTv31)
            self.mqtt.connect(
                self.config.get("mqtt", "host"),
                self.config.getint("mqtt", "port"),
            )
            self.mqtt.loop_start()
            self.configure_mqtt_topics()
            logger.info("MQTT client connected")
        else:
            self.mqtt = None



        self.configure_timed_read()

    def configure_mqtt_topics(self):
        setpoint_topic = f"{self.base_topic}/setpoint"
        self.mqtt.subscribe(setpoint_topic)
        self.mqtt.message_callback_add(setpoint_topic, self.temperature_setpoint_changed)

        pid_topic = f"{self.base_topic}/pid/+"
        self.mqtt.subscribe(pid_topic)
        self.mqtt.message_callback_add(pid_topic, self.pid_changed)

    def temperature_setpoint_changed(self, client, userdata, message):
        try:
            data = float(message.payload)
        except ValueError:
            logger.error(f"Failed to parse {message.payload} into float")
            return
        self.control.set_temperature(data)

    def pid_changed(self, client, userdata, message: mqtt.MQTTMessage):
        target = message.topic.split("/")[-1]
        p = i = d = None
        if target == "p":
            p = float(message.payload)
        elif target == "i":
            i = float(message.payload)
        elif target == "d":
            d = float(message.payload)
        else:
            logger.error(f"Unrecognized parameter: {target}")
            return
        self.control.set_pid(p, i, d)

    def configure_timed_read(self):
        interval = self.config.getfloat("fp50", "interval")

        if interval > 0:
            # enabled
            rx.interval(interval, scheduler=NewThreadScheduler()).pipe(
                operators.flat_map(lambda x: self.control.get_power()),
                operators.map(lambda x: self.upload_power(x)),
                operators.delay(self.config.getfloat("fp50", "query_delay")),
                operators.flat_map(lambda x: self.control.get_internal_temperature()),
                operators.map(lambda x: self.upload_internal_temperature(x)),
                operators.catch(error_handler)
            ).subscribe()

    def upload_power(self, power):
        if power is None:
            return
        if self.influxdb:
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

        if self.mqtt:
            self.mqtt.publish(f"{self.base_topic}/power", bytes(str(power), "ascii"))

    def upload_internal_temperature(self, internal_temperature):
        if internal_temperature is None:
            return

        if self.influxdb:
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

        if self.mqtt:
            self.mqtt.publish(f"{self.base_topic}/temperature", bytes(str(internal_temperature), "ascii"))
