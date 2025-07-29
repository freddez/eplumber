import datetime
import json
import logging
import operator
import statistics
from collections import deque
from collections.abc import Callable
from typing import Literal

import paho.mqtt.client as mqtt_client
import requests
from jsonpath_ng import parse
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

import mqtt
from notification import send_action_notification

logger = logging.getLogger(__name__)


class Sensors(BaseModel):
    mqtt: str = ""

    def add_mqtt(self):
        pass

    def add(self, sensor):
        self[sensor.nam] = sensor

    def start(self):
        pass


SENSORS = {}


class Sensor(BaseModel):
    name: str = Field(title="Sensor name")
    route: str = Field(title="mqtt path")
    json_path: str | None = None
    return_type: Literal["float", "int", "str", "bool"] = "float"
    connected: bool = False
    ready: bool = False
    value_list_length: int = 5
    values: deque[float | int | bool | str] | None = None

    def model_post_init(self, __context) -> None:
        if self.values is None:
            self.values = deque(maxlen=self.value_list_length)

    def __str__(self):
        return str(self.name)

    @property
    def mean(self) -> float | int | bool | str | None:
        if not self.values:
            return None
        if self.return_type == "bool":
            return self.values[-1]
        return float(statistics.mean(self.values))

    @property
    def last(self):
        if not self.values:
            return None
        return self.values[-1]

    def _json_path_value(self, data):
        if isinstance(data, bytes) or isinstance(data, str):
            data = json.loads(data)
        jsonpath_expr = parse(self.json_path)
        matches = jsonpath_expr.find(data)
        if matches:
            return matches[0].value
        else:
            logging.error(
                f"JSON path '{self.json_path}' not found in response for {self.name}"
            )
            return None

    def _get_parsed_value(self, value):
        parsed_value = None
        if self.return_type == "bool":
            if isinstance(value, bool):
                parsed_value = value
            elif isinstance(value, str):
                parsed_value = value.lower() in ("true", "1", "on", "yes")
            else:
                parsed_value = bool(value)
        elif self.return_type == "int":
            parsed_value = int(float(value))
        elif self.return_type == "float":
            parsed_value = float(value)
        else:
            parsed_value = str(value)
        return parsed_value

    def add(self, value):
        if self.json_path:
            parsed_value = self._json_path_value(value)
        else:
            parsed_value = self._get_parsed_value(value)
        if parsed_value is None:
            return None
        logging.debug(f"{self.name}.add({parsed_value}) mean:{self.mean}")
        self.connected = True
        if self.values is not None:
            self.values.append(parsed_value)
        return parsed_value


class MqttSensor(Sensor):
    type: Literal["mqtt"] = "mqtt"


class HttpSensor(Sensor):
    type: Literal["http"] = "http"

    def get_add_value(self):
        try:
            response = requests.get(self.route, timeout=10)
            response.raise_for_status()
            data = response.json()
            self.add(data)
            logging.debug(f"HTTP sensor {self.name}: {data}")
        except Exception as e:
            logging.error(f"Error fetching HTTP sensor {self.name}: {e}")
            self.connected = False


class TimeSensor(Sensor):
    type: Literal["time"] = "time"
    route: str = ""
    connected: bool = True

    @property
    def mean(self):
        return datetime.datetime.now().strftime("%H:%M")


def add_sensor(sensor):
    if sensor.route in SENSORS:
        raise ValueError("Sensor route alreasy exists")
    SENSORS[sensor.route] = sensor


class SensorD(BaseModel):
    ss: dict[str, MqttSensor | HttpSensor | TimeSensor] = {
        "time": TimeSensor(name="time", return_type="str")
    }

    def add(self, sensor_data: dict | MqttSensor | HttpSensor | TimeSensor):
        if isinstance(sensor_data, dict):
            sensor_type = sensor_data.get("type", "mqtt")
            if sensor_type == "mqtt":
                sensor = MqttSensor(**sensor_data)
            elif sensor_type == "http":
                sensor = HttpSensor(**sensor_data)
            elif sensor_type == "time":
                sensor = TimeSensor(**sensor_data)
            else:
                raise ValueError(f"Unknown sensor type: {sensor_type}")
        else:
            sensor = sensor_data

        self.ss[sensor.route] = sensor
        self.ss[sensor.name] = sensor
        return sensor

    def __getitem__(self, key):
        return self.ss[key]

    def add_value(self, route, value):
        self.ss[route].add(value)

    def keys(self):
        return self.ss.keys()

    def values(self):
        return self.ss.values()


VALID_OPERATOR = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


class Test(BaseModel):
    sensor: MqttSensor | HttpSensor | TimeSensor
    op: str
    _operator: Callable = PrivateAttr()

    @property
    def operator(self):
        return self._operator

    value: float | str | int

    @field_validator("op", mode="after")
    @classmethod
    def validate_op(cls, v):
        valid_operators = VALID_OPERATOR.keys()
        if v not in valid_operators:
            raise ValueError(f"Invalid operator '{v}'. Must be one of: {valid_operators}")
        return v

    def __init__(self, **data):
        super().__init__(**data)
        self._operator = VALID_OPERATOR[self.op]


class Action(BaseModel):
    name: str
    route: str
    _web_api = None
    _recipients = None

    def set_web_api(self, web_api):
        self._web_api = web_api

    def set_recipients(self, recipients):
        self._recipients = recipients

    def _send_email_notification(self, rule_context=None):
        send_action_notification(self._recipients, self.name, rule_context)

    def do(self, rule_context=None):
        logger.info(f"Do {self.name}")
        try:
            response = requests.get(self.route)
            if self._web_api:
                self._web_api.log_action(self.name, self.route)
            self._send_email_notification(rule_context)
            logger.debug(f"Action {self.name} executed: {response.status_code}")
        except Exception as e:
            logger.error(f"Action {self.name} failed: {e}")


class Rule(BaseModel):
    name: str
    tests: list[Test]
    action: Action
    active: bool = True


class ConfigRule(BaseModel):
    name: str
    tests: list[tuple[str, str, float | str | int]]
    action: str
    active: bool = True


class Mqtt(BaseModel):
    host: str
    port: int
    username: str
    password: str
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: mqtt_client.Client | None = None

    def set_client(self, sensord):
        mqttc = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        mqttc.on_connect = mqtt.on_connect
        mqttc.on_message = mqtt.on_message

        mqttc.user_data_set(sensord)
        if self.username:
            mqttc.username_pw_set(self.username, self.password)
        try:
            mqttc.connect(self.host)
        except OSError:
            raise ConnectionError(f"Could not connect to {self.host}")
        mqttc.loop_start()  # threaded client interface


class Global(BaseModel):
    recipients: list[str] = []


class Config(BaseModel):
    global_: Global | None = Field(None, alias="global")
    mqtt: Mqtt
    sensors: list[dict]
    actions: list[Action]
    rules: list[ConfigRule]
