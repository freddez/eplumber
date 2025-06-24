from pydantic import BaseModel, ConfigDict
from pathlib import Path
import appdirs
import json
import logging
from typing import Optional
import models
from notification import send_startup_notification
import threading
from web_api import WebAPI

logger = logging.getLogger(__name__)

CFG_FILENAME = "eplumber.json"


class Eplumber(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    sensord: models.SensorD = models.SensorD()
    config: Optional[models.Config] = None
    rules: list[models.Rule] = []
    http_sensors: list[models.HttpSensor] = []
    _http_timer: Optional[threading.Timer] = None
    _rules_timer: Optional[threading.Timer] = None
    _cached_rules_data: list = []
    web_api: Optional[WebAPI] = None
    _config_path: Optional[Path] = None
    log_level: str = "info"

    def __init__(self, log_level="info", **data):
        super().__init__(log_level=log_level, **data)

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
            logger.error(f"{CFG_FILENAME} not found")
            return

        self._load_config_data(cfg_json)
        self._start_http_polling()
        self._start_rule_polling()
        self._start_web_api()

    def _load_config_data(self, cfg_json):
        """Load configuration data and set up sensors/rules"""
        # Clear existing data
        self.sensord = models.SensorD()
        self.rules = []
        self.http_sensors = []

        # Stop existing timers
        if self._http_timer:
            self._http_timer.cancel()
        if self._rules_timer:
            self._rules_timer.cancel()

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
            # Set active to True if not specified or empty
            active = cfg_rule.active if cfg_rule.active is not None else True
            rule = models.Rule(
                name=cfg_rule.name,
                tests=tests,
                action=action_d[cfg_rule.action],
                active=active,
            )
            self.rules.append(rule)

        # Set web_api reference and recipients for all actions
        recipients = self.config.global_.recipients if self.config.global_ else []
        for rule in self.rules:
            if self.web_api:
                rule.action.set_web_api(self.web_api)
            rule.action.set_recipients(recipients)

        self.config.mqtt.set_client(self.sensord)

        # Send startup notification
        if recipients:
            send_startup_notification(recipients)

    def _poll_http_sensors(self):
        for sensor in self.http_sensors:
            try:
                sensor.get_add_value()
            except Exception as e:
                logger.error(f"Error polling HTTP sensor {sensor.name}: {e}")
        self._http_timer = threading.Timer(10.0, self._poll_http_sensors)
        self._http_timer.start()

    def _start_http_polling(self):
        if self.http_sensors:
            self._poll_http_sensors()

    def _pool_rules(self):
        """Evaluate all rules and trigger actions in a dedicated thread"""
        try:
            result = []
            for rule in self.rules:
                rule_tests = []
                for test in rule.tests:
                    try:
                        sensor_name = str(test.sensor.name)
                        operator_str = str(test.op)
                        test_value = test.value
                        current_value = test.sensor.mean
                        if current_value is not None and test.operator:
                            passes = bool(test.operator(current_value, test_value))
                        else:
                            passes = False
                        if isinstance(test_value, (int, float, str, bool)):
                            safe_test_value = test_value
                        else:
                            safe_test_value = str(test_value)
                        if (
                            isinstance(current_value, (int, float, str, bool))
                            or current_value is None
                        ):
                            safe_current_value = (
                                round(current_value, 2)
                                if isinstance(current_value, float)
                                else current_value
                            )
                        else:
                            safe_current_value = str(current_value)
                        test_result = {
                            "sensor_name": sensor_name,
                            "operator": operator_str,
                            "value": safe_test_value,
                            "current_sensor_value": safe_current_value,
                            "passes": passes,
                        }
                        rule_tests.append(test_result)
                    except Exception as e:
                        logger.error(f"Error evaluating test for rule {rule.name}: {e}")
                        continue
                all_tests_pass = bool(all(t["passes"] for t in rule_tests))
                if all_tests_pass and rule.active:
                    rule.action.do(rule)
                rule_result = {
                    "action_name": f"{rule.name} ⇒ {rule.action.name}",
                    "tests": rule_tests,
                    "all_tests_pass": all_tests_pass,
                    "active": rule.active,
                }
                result.append(rule_result)
            # Cache the results for web API
            self._cached_rules_data = result
        except Exception as e:
            logger.error(f"Error in rule evaluation: {e}")
        # Schedule next evaluation
        self._rules_timer = threading.Timer(5.0, self._pool_rules)
        self._rules_timer.start()

    def _start_rule_polling(self):
        if self.rules:
            self._pool_rules()

    def _start_web_api(self):
        if not self.web_api:
            self.web_api = WebAPI(self)

            self.web_api.start_server(log_level=self.log_level)
            logger.info("🌐 Web interface available at http://localhost:8000")

        # Set web_api reference for all actions
        for rule in self.rules:
            rule.action.set_web_api(self.web_api)
