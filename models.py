import datetime
import operator
import requests
import logging
from pydantic import BaseModel, Field, field_validator, ConfigDict, PrivateAttr
from typing import Callable
from collections import deque, UserDict
import statistics
from typing import Annotated, Deque, Union, Optional, Tuple
import paho.mqtt.client as mqtt_client
import mqtt

logger = logging.getLogger(__name__)


class Sensors(BaseModel, UserDict):
    mqtt: str = ""

    def add_mqtt(self):
        pass

    def add(self, sensor):
        self[sensor.nam] = sensor

    def start(self):
        pass

    def __init__(self, **data):
        # Let BaseModel handle validation and assignment
        super().__init__(**data)
        # Now initialize UserDict with model's dict
        UserDict.__init__(self, self.dict())


SENSORS = {}
ALLOWED_TYPES = ("float", "int", "str", "bool")


class Sensor(BaseModel):
    name: str = Field(title="Sensor name")
    route: str = Field(title="mqtt path")
    type: str = Field()
    connected: bool = False
    ready: bool = False
    values: Annotated[Deque[float], Field(deque(maxlen=10), max_length=10)]

    def __str__(self):
        return str(self.name)

    @field_validator("type", mode="after")
    @classmethod
    def allowed_type(cls, v):
        valid_operators = VALID_OPERATOR
        if v not in valid_operators:
            raise ValueError(
                f"Invalid operator '{v}'. Must be one of: {list(valid_operators.keys())}"
            )
        return v

    @property
    def mean(self) -> float | int | bool | str | None:
        if not self.values:
            return None
        if self.type == "bool":
            return self.values[-1]
        return float(statistics.mean(self.values))

    @property
    def last(self):
        return self.values[-1]

    def add(self, value):
        logging.debug(f"{self.name}.add({value}) mean:{self.mean}")
        self.values.append(value)


class MqttSensor(Sensor):
    pass


class HttpSensor(Sensor):

    def get_value(self):
        value = requests.get(self.route)
        self.add(value)


class TimeSensor(Sensor):
    route = ""

    @property
    def mean(self):
        return datetime.datetime.now().strftime("%H:%M")


def add_sensor(sensor):
    if sensor.route in SENSORS:
        raise ValueError("Sensor route alreasy exists")
    SENSORS[sensor.route] = sensor


class SensorD(BaseModel):
    ss: dict[str, Union[MqttSensor, HttpSensor, TimeSensor]] = {"time": TimeSensor()}

    def add(self, sensor: MqttSensor):
        self.ss[sensor.route] = sensor
        self.ss[sensor.name] = sensor

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
    # Add more operators as needed
}


class Test(BaseModel):
    sensor: Union[MqttSensor, TimeSensor]
    op: str
    _operator: Callable = PrivateAttr()

    @property
    def operator(self):
        return self._operator

    value: Union[float, str, int]

    def validate_op(cls, v):
        valid_operators = VALID_OPERATOR
        if v not in valid_operators:
            raise ValueError(
                f"Invalid operator '{v}'. Must be one of: {list(valid_operators.keys())}"
            )
        return v

    def __init__(self, **data):
        super().__init__(**data)
        self._operator = VALID_OPERATOR[self.op]


class Action(BaseModel):
    name: str
    route: str

    def do(self):
        print(f"Do {self.name}")
        requests.get(self.route)


class Rule(BaseModel):
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
        # mqttc.on_subscribe = on_subscribe
        # mqttc.on_unsubscribe = on_unsubscribe

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
    sensors: list[MqttSensor]
    actions: list[Action]
    rules: list[ConfigRule]
