from pydantic import BaseModel, ConfigDict
from pathlib import Path
import appdirs
import json
from typing import Optional
import models
import threading
from web_api import WebAPI
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

CFG_FILENAME = "eplumber.json"


class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, eplumber_instance):
        self.eplumber = eplumber_instance
        super().__init__()

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(CFG_FILENAME):
            print(f"Config file changed: {event.src_path}")
            self.eplumber.reload_config()


class Eplumber(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    sensord: models.SensorD = models.SensorD()
    config: Optional[models.Config] = None
    rules: list[models.Rule] = []
    http_sensors: list[models.HttpSensor] = []
    _http_timer: Optional[threading.Timer] = None
    web_api: Optional[WebAPI] = None
    _file_observer: Optional[Observer] = None
    _config_path: Optional[Path] = None

    def get_config(self):
        cfg_json = None
        for path in ("", appdirs.user_config_dir()):
            cfg_path = Path(path) / CFG_FILENAME
            if cfg_path.exists():
                self._config_path = cfg_path
                cfg_file = open(cfg_path, "r")
                cfg_json = json.load(cfg_file)
                break
        if cfg_json is None:
            print(f"{CFG_FILENAME} not found")
            return

        self._load_config_data(cfg_json)
        self._start_file_watcher()
        self._start_http_polling()
        self._start_web_api()

    def _load_config_data(self, cfg_json):
        """Load configuration data and set up sensors/rules"""
        # Clear existing data
        self.sensord = models.SensorD()
        self.rules = []
        self.http_sensors = []

        # Stop existing HTTP timer
        if self._http_timer:
            self._http_timer.cancel()

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
            rule = models.Rule(
                name=cfg_rule.name, tests=tests, action=action_d[cfg_rule.action]
            )
            self.rules.append(rule)

        # Set web_api reference for all actions if web_api exists
        if self.web_api:
            for rule in self.rules:
                rule.action.set_web_api(self.web_api)

        self.config.mqtt.set_client(self.sensord)

    def reload_config(self):
        """Reload configuration from file"""
        if not self._config_path or not self._config_path.exists():
            print("Config file not found for reload")
            return

        try:
            with open(self._config_path, "r") as cfg_file:
                cfg_json = json.load(cfg_file)
            self._load_config_data(cfg_json)
            self._start_http_polling()
            print("Configuration reloaded successfully")
        except Exception as e:
            print(f"Error reloading config: {e}")

    def _start_file_watcher(self):
        """Start watching the config file for changes"""
        if self._config_path:
            self._file_observer = Observer()
            handler = ConfigFileHandler(self)
            self._file_observer.schedule(
                handler, str(self._config_path.parent), recursive=False
            )
            self._file_observer.start()
            print(f"Watching config file: {self._config_path}")

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

    def _start_web_api(self):
        if not self.web_api:
            self.web_api = WebAPI(self)
            self.web_api.start_server()
            print("🌐 Web interface available at http://localhost:8000")

        # Set web_api reference for all actions
        for rule in self.rules:
            rule.action.set_web_api(self.web_api)

    def run(self):
        while True:
            for rule in self.rules:
                valid_rule = False
                for test in rule.tests:
                    if test.operator and test.operator(test.sensor.mean, test.value):
                        valid_rule = True
                if valid_rule:
                    rule.action.do()
