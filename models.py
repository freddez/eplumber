import datetime
import operator
import requests
import logging
from pydantic import BaseModel, Field, field_validator, ConfigDict, PrivateAttr
from typing import Callable, Literal
from collections import deque
import statistics
from typing import Annotated, Deque, Union, Optional, Tuple
import paho.mqtt.client as mqtt_client
import mqtt
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

    # def __init__(self, **data):
    #     # Let BaseModel handle validation and assignment
    #     super().__init__(**data)
    #     # Now initialize UserDict with model's dict
    #     # UserDict.__init__(self, self.dict())


SENSORS = {}


class Sensor(BaseModel):
    name: str = Field(title="Sensor name")
    route: str = Field(title="mqtt path")
    return_type: Literal["float", "int", "str", "bool"] = "float"
    connected: bool = False
    ready: bool = False
    values: Annotated[Deque[float | bool], Field(deque(maxlen=10), max_length=10)]

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
        return self.values[-1]

    def add(self, value):
        logging.debug(f"{self.name}.add({value}) mean:{self.mean}")
        self.connected = True
        self.values.append(value)


class MqttSensor(Sensor):
    type: Literal["mqtt"] = "mqtt"


class HttpSensor(Sensor):
    type: Literal["http"] = "http"
    json_path: Optional[str] = None

    def get_add_value(self):
        try:
            response = requests.get(self.route, timeout=10)
            response.raise_for_status()
            data = response.json()
            if self.json_path:
                jsonpath_expr = parse(self.json_path)
                matches = jsonpath_expr.find(data)
                if matches:
                    value = matches[0].value
                else:
                    logging.error(
                        f"JSON path '{self.json_path}' not found in response for {self.name}"
                    )
                    return
            else:
                value = data
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
            self.add(parsed_value)
            logging.debug(f"HTTP sensor {self.name}: {parsed_value}")
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

    def set_web_api(self, web_api):
        self._web_api = web_api

    def do(self):
        print(f"Do {self.name}")
        try:
            response = requests.get(self.route)
            if self._web_api:
                self._web_api.log_action(self.name, self.route)
            logger.info(f"Action {self.name} executed: {response.status_code}")
        except Exception as e:
            logger.error(f"Action {self.name} failed: {e}")


class Rule(BaseModel):
    name: str
    tests: list[Test]
    action: Action


class ConfigRule(BaseModel):
    name: str
    tests: list[Tuple[str, str, Union[float, str, int]]]
    action: str


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


class Config(BaseModel):
    mqtt: Mqtt
    sensors: list[dict]
    actions: list[Action]
    rules: list[ConfigRule]
