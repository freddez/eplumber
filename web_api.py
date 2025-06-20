from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from datetime import datetime
import models
import threading
import uvicorn
from collections import deque
import json
import logging

logger = logging.getLogger(__name__)


class WebAPI:
    def __init__(self, eplumber_instance):
        self.eplumber = eplumber_instance
        self.app = FastAPI(title="Eplumber Monitor", version="1.0.0")
        self.action_history = deque(maxlen=100)

        # Mount static files with cache control
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/api/sensors")
        async def get_sensors():
            sensors_data = []
            unique_sensors = set()

            for sensor in self.eplumber.sensord.values():
                if id(sensor) in unique_sensors:
                    continue
                unique_sensors.add(id(sensor))

                try:
                    values = list(sensor.values)
                    sensor_data = {
                        "name": sensor.name,
                        "route": sensor.route,
                        "type": sensor.type,
                        "return_type": sensor.return_type,
                        "connected": sensor.connected,
                        "ready": sensor.ready,
                        "mean": round(sensor.mean, 2) if isinstance(sensor.mean, float) else sensor.mean,
                        "last": round(sensor.last, 2) if isinstance(sensor.last, float) else sensor.last,
                        "values": [round(v, 2) if isinstance(v, float) else v for v in values],
                        "value_count": len(values),
                    }
                    sensors_data.append(sensor_data)

                except Exception as e:
                    logger.error(
                        f"Error serializing sensor {getattr(sensor, 'name', 'unknown')}: {e}"
                    )
                    continue

            return JSONResponse(content={"sensors": sensors_data})

        @self.app.get("/api/sensors/{sensor_name}")
        async def get_sensor(sensor_name: str):
            try:
                sensor = self.eplumber.sensord[sensor_name]
                mean_value = sensor.mean
                last_value = sensor.last if sensor.values else None
                sensor_data = {
                    "name": sensor.name,
                    "route": sensor.route,
                    "type": sensor.type,
                    "return_type": sensor.return_type,
                    "connected": sensor.connected,
                    "ready": sensor.ready,
                    "mean": mean_value,
                    "last": last_value,
                    "values": list(sensor.values),
                    "value_count": len(sensor.values),
                }
                return JSONResponse(content=sensor_data)
            except KeyError:
                raise HTTPException(status_code=404, detail="Sensor not found")
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Error reading sensor: {str(e)}"
                )

        @self.app.get("/api/actions/history")
        async def get_action_history():
            return JSONResponse(content={"actions": list(self.action_history)})

        @self.app.get("/api/rules")
        async def get_rules():
            try:
                response_data = []

                for rule in self.eplumber.rules:
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
                                safe_current_value = round(current_value, 2) if isinstance(current_value, float) else current_value
                            else:
                                safe_current_value = str(current_value)

                            test_dict = {
                                "sensor_name": sensor_name,
                                "operator": operator_str,
                                "value": safe_test_value,
                                "current_sensor_value": safe_current_value,
                                "passes": passes,
                            }
                            rule_tests.append(test_dict)

                        except Exception:
                            continue
                    all_tests_pass = bool(all(t["passes"] for t in rule_tests))
                    if all_tests_pass and rule.active:
                        rule.action.do(rule)
                    rule_dict = {
                        "action_name": f"{rule.name} ⇒ {rule.action.name}",
                        "tests": rule_tests,
                        "all_tests_pass": all_tests_pass,
                        "active": rule.active,
                    }
                    response_data.append(rule_dict)

                return JSONResponse(content={"rules": response_data})

            except Exception:
                return JSONResponse(content={"rules": []})

        @self.app.get("/api/config")
        async def get_config():
            try:
                if self.eplumber._config_path and self.eplumber._config_path.exists():
                    with open(self.eplumber._config_path, "r") as f:
                        config_data = json.load(f)
                    return JSONResponse(content={"config": config_data})
                else:
                    return JSONResponse(
                        content={"error": "Config file not found"}, status_code=404
                    )
            except Exception as e:
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.put("/api/config")
        async def update_config(request: Request):
            try:
                body = await request.json()
                config_data = body.get("config")

                if not config_data:
                    return JSONResponse(
                        content={"error": "No config data provided"}, status_code=400
                    )

                # Validate config by trying to create Config object
                try:
                    models.Config(**config_data)
                except Exception as validation_error:
                    return JSONResponse(
                        content={"error": f"Invalid config: {validation_error}"},
                        status_code=400,
                    )

                # Save to file
                if self.eplumber._config_path:
                    with open(self.eplumber._config_path, "w") as f:
                        json.dump(config_data, f, indent=2)

                    # Config will be automatically reloaded by systemd service restart
                    return JSONResponse(content={"message": "Config saved successfully"})
                else:
                    return JSONResponse(
                        content={"error": "Config file path not found"}, status_code=500
                    )

            except Exception as e:
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.post("/api/config/reload")
        async def reload_config():
            # Config reload is now handled by systemd service restart
            return JSONResponse(content={"message": "Config reload handled by systemd - service will restart automatically"})

        @self.app.get("/")
        async def get_dashboard():
            response = FileResponse("static/index.vue", media_type="text/html")
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        @self.app.get("/config.html")
        async def get_config_editor():
            response = FileResponse("static/config.vue", media_type="text/html")
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        @self.app.get("/static/css/{filename}")
        async def get_css(filename: str):
            response = FileResponse(f"static/css/{filename}", media_type="text/css")
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        @self.app.get("/favicon.ico")
        async def get_favicon():
            return FileResponse("static/favicon.svg", media_type="image/svg+xml")

    def log_action(self, action_name: str, route: str):
        self.action_history.append(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "name": action_name,
                "route": route,
            }
        )

    def start_server(self, host="0.0.0.0", port=8000, log_level="info"):
        def run_server():
            uvicorn.run(self.app, host=host, port=port, log_level=log_level)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        return server_thread
