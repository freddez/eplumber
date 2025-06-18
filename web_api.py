from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
import models
import threading
import uvicorn
from collections import deque
import json


class WebAPI:
    def __init__(self, eplumber_instance):
        self.eplumber = eplumber_instance
        self.app = FastAPI(title="Eplumber Monitor", version="1.0.0")
        self.action_history = deque(maxlen=100)

        # Mount static files
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
                        "mean": sensor.mean,
                        "last": sensor.last,
                        "values": list(values),
                        "value_count": len(values),
                    }
                    sensors_data.append(sensor_data)

                except Exception as e:
                    print(
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
                                safe_current_value = current_value
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

                    rule_dict = {
                        "action_name": f"{rule.name} ({rule.action.name})",
                        "tests": rule_tests,
                        "all_tests_pass": bool(all(t["passes"] for t in rule_tests)),
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

                    # Config will be automatically reloaded by file watcher
                    return JSONResponse(content={"message": "Config saved successfully"})
                else:
                    return JSONResponse(
                        content={"error": "Config file path not found"}, status_code=500
                    )

            except Exception as e:
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.post("/api/config/reload")
        async def reload_config():
            try:
                self.eplumber.reload_config()
                return JSONResponse(content={"message": "Config reloaded successfully"})
            except Exception as e:
                return JSONResponse(content={"error": str(e)}, status_code=500)

        @self.app.get("/")
        async def get_dashboard():
            return FileResponse("static/index.vue", media_type="text/html")

        @self.app.get("/config.html")
        async def get_config_editor():
            return FileResponse("static/config.vue", media_type="text/html")

        @self.app.get("/favicon.ico")
        async def get_favicon():
            return FileResponse("static/favicon.svg", media_type="image/svg+xml")

    def log_action(self, action_name: str, route: str):
        """Log an action execution"""
        self.action_history.append(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "name": action_name,
                "route": route,
            }
        )

    def start_server(self, host="0.0.0.0", port=8000):
        """Start the FastAPI server in a separate thread"""

        def run_server():
            uvicorn.run(self.app, host=host, port=port, log_level="debug")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        return server_thread
