import logging

logger = logging.getLogger(__name__)


def on_message(client, sensord, message):
    route = message.topic
    value = message.payload
    logger.debug(f"Message[{route}] : {value}")
    sensord.add_value(route, value)


def on_connect(client, sensord, flags, reason_code, properties):
    logger.info("Connected")
    if reason_code.is_failure:
        logger.error(
            f"Failed to connect: {reason_code}. loop_forever() will retry connection"
        )
        return
    for route in sensord.keys():
        logger.info(f"Subscribe to {route}")
        client.subscribe(route)
