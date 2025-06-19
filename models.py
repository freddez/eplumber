import datetime
import operator
import requests
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import BaseModel, Field, field_validator, ConfigDict, PrivateAttr
from typing import Callable, Literal
from collections import deque
import statistics
from typing import Annotated, Deque, Union, Optional, Tuple
import paho.mqtt.client as mqtt_client
import mqtt
import json
from jsonpath_ng import parse

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
    json_path: Optional[str] = None
    return_type: Literal["float", "int", "str", "bool"] = "float"
    connected: bool = False
    ready: bool = False
    values: Annotated[Deque[float | int | bool], Field(deque(maxlen=10), max_length=10)]

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
    ss: dict[str, Union[MqttSensor, HttpSensor, TimeSensor]] = {
        "time": TimeSensor(name="time", return_type="str")
    }

    def add(self, sensor_data: Union[dict, MqttSensor, HttpSensor, TimeSensor]):
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
    sensor: Union[MqttSensor, HttpSensor, TimeSensor]
    op: str
    _operator: Callable = PrivateAttr()

    @property
    def operator(self):
        return self._operator

    value: Union[float, str, int]

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
        if not self._recipients:
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = "eplumber@localhost"
            msg["To"] = ", ".join(self._recipients)
            msg["Subject"] = f"Eplumber Action: {self.name}"

            body = f"Action '{self.name}' has been executed.\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            if rule_context:
                body += f"Rule: {rule_context.name}\n\nTest Results:\n"
                for test in rule_context.tests:
                    current_value = test.sensor.mean
                    if isinstance(current_value, float):
                        current_value = round(current_value, 2)
                    passes = (
                        test.operator(current_value, test.value)
                        if current_value is not None
                        else False
                    )
                    status = "✅ PASS" if passes else "❌ FAIL"
                    body += f"  {status} {test.sensor.name}: {current_value} {test.op} {test.value}\n"

            msg.attach(MIMEText(body, "plain"))
            server = smtplib.SMTP("localhost", 25)
            server.sendmail("eplumber@localhost", self._recipients, msg.as_string())
            server.quit()
            logger.info(f"Email notification sent for action {self.name}")
        except Exception as e:
            logger.error(f"Failed to send email notification for action {self.name}: {e}")

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
    tests: list[Tuple[str, str, Union[float, str, int]]]
    action: str
    active: bool = True


class Mqtt(BaseModel):
    host: str
    port: int
    username: str
    password: str
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: Optional[mqtt_client.Client] = None

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
    global_: Optional[Global] = Field(None, alias="global")
    mqtt: Mqtt
    sensors: list[dict]
    actions: list[Action]
    rules: list[ConfigRule]
