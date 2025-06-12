from pydantic import BaseModel
from pathlib import Path
import appdirs
import json
from typing import Optional
import models
import threading

CFG_FILENAME = "eplumber.json"


class Eplumber(BaseModel):
    sensord: models.SensorD = models.SensorD()
    config: Optional[models.Config] = None
    rules: list[models.Rule] = []
    http_sensors: list[models.HttpSensor] = []
    _http_timer: Optional[threading.Timer] = None

    def get_config(self):
        cfg_json = None
        for path in ("", appdirs.user_config_dir()):
            cfg_path = Path(path) / CFG_FILENAME
            if cfg_path.exists():
                cfg_file = open(cfg_path, "r")
                cfg_json = json.load(cfg_file)
                break
        if cfg_json is None:
            print(f"{CFG_FILENAME} not found")
            return
        self.config = models.Config(**cfg_json)
        for s in self.config.sensors:
            sensor = self.sensord.add(s)
            if isinstance(sensor, models.HttpSensor):
                self.http_sensors.append(sensor)
        action_d = {a.name: a for a in self.config.actions}
        for cfg_rule in self.config.rules:
            tests = []
            for sensor_name, op, value in cfg_rule.tests:
                test = models.Test(sensor=self.sensord[sensor_name], op=op, value=value)
                tests.append(test)
            rule = models.Rule(tests=tests, action=action_d[cfg_rule.action])
            self.rules.append(rule)
        self.config.mqtt.set_client(self.sensord)
        self._start_http_polling()

    def _poll_http_sensors(self):
        for sensor in self.http_sensors:
            try:
                sensor.get_value()
            except Exception as e:
                print(f"Error polling HTTP sensor {sensor.name}: {e}")

        self._http_timer = threading.Timer(10.0, self._poll_http_sensors)
        self._http_timer.start()

    def _start_http_polling(self):
        if self.http_sensors:
            self._poll_http_sensors()

    def run(self):
        while True:
            for rule in self.rules:
                valid_rule = False
                for test in rule.tests:
                    if test.operator and test.operator(test.sensor.mean, test.value):
                        valid_rule = True
                if valid_rule:
                    rule.action.do()
