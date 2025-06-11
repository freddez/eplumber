def on_message(client, sensord, message):
    route = message.topic
    value = float(message.payload)
    print(f"Message[{route}] : {value}")
    sensord.add_value(route, value)


def on_connect(client, sensord, flags, reason_code, properties):
    print("Connected")
    if reason_code.is_failure:
        print(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
        return
    for route in sensord.keys():
        print(f"Subscribe to {route}")
        client.subscribe(route)
