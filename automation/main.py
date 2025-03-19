#!/usr/bin/env python3

import argparse
import asyncio
from dataclasses import dataclass
import importlib
import logging
import sys

from aiomqtt import Client
import aiosmtplib
from dotenv import DotEnv
from email.message import EmailMessage

import automation.config as config

logger = logging.getLogger()
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter("%(asctime)s %(module)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class Secrets:
    pass


async def init():
    # set log level of modules logger
    for lg_name, lg_config in config.loggers.items():
        module_name = f"sail.{lg_name}"
        try:
            module = sys.modules[module_name]
        except KeyError:
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                logger.warning(f"module {module_name} not found")
                continue
        module_logger = getattr(module, "logger")
        module_logger.setLevel(lg_config.level)


async def run(config_filename: str, secrets):
    config.read(config_filename)

    await init()

    logger.info("started")
    try:
        async with Client(config.mqtt.host, config.mqtt.port) as client:
            await client.subscribe("home/doorbell/button")
            async for message in client.messages:
                if message.payload.decode() == "pressed":
                    await client.publish("home/doorbell/bell")

                    message = EmailMessage()
                    message["From"] = secrets.mail_from,
                    message["To"] = secrets.mail_to
                    message["Subject"] = "Ding dong !"
                    message.set_content("On sonne à la porte")
                    try:
                        await aiosmtplib.send(
                            message,
                            hostname=config.smtp.host,
                            port=config.smtp.port,
                            username=secrets.smtp_username,
                            password=secrets.smtp_password
                        )
                    except Exception as exc:
                        logger.error(f"{exc}")
    except KeyboardInterrupt:
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="config.toml")
    args = parser.parse_args()

    # get secrets
    dotenv = DotEnv()
    if not dotenv.has("MAIL_FROM") or not dotenv.has("MAIL_TO") or \
            not dotenv.has("SMTP_USERNAME") or not dotenv.has("SMTP_PASSWORD"):
        sys.stderr.write(
            "Please define environment variables MAIL_FROM, MAIL_TO, "
            "SMTP_USERNAME and SMTP_PASSWORD either by hand, in an init script "
            "(bashrc or other) or in the .env file.\n"
        )
        sys.exit(1)

    # store secrets in memory
    env_secrets = dotenv.all()
    secrets = Secrets()
    for k, v in env_secrets.items():
        setattr(secrets, k.lower(), v)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run(args.config, secrets))
    except KeyboardInterrupt:
        pass
    finally:
        # loop.run_until_complete(close())
        loop.stop()
        logger.info("done")


if __name__ == "__main__":
    main()
