import models

s = models.MqttSensor(name="coucou", route="route")
print(s)
ss = models.SensorD()
ss.add(s)
print(ss)
ss.add(2)
