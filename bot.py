import ast
import asyncio
import json
import logging
import os
from itertools import cycle

import telebot.types
from dotenv import load_dotenv
from nats.js import JetStreamContext
from nats.aio.msg import Msg as MsgNats
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_helper import ApiTelegramException
from telebot.util import split_string

from model import Env, Msg, Buffer
from emojies import replace_from_emoji
from util import nats_connect, get_data_env


def get_env(x):
    modal = x(**os.environ)
    return modal.model_copy(
        update={"TELEGRAM_BOT_TOKENS": ast.literal_eval(modal.TELEGRAM_BOT_TOKENS)}
    )


load_dotenv()
env = get_data_env(
    Env,
    get_env
)

bots = [
    AsyncTeleBot(token)
    for token in env.TELEGRAM_BOT_TOKENS
]  # Bypass rate limit
bot = bots[0]

logging.info("count bots: %s", len(bots))
bots = cycle(bots)

js: JetStreamContext = None
buffer: dict[int | str, Buffer] = {}

logging.basicConfig(
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s'
)
log = logging.getLogger("root")
log.setLevel(getattr(logging, env.log_level.upper()))

def generate_message(_msg: telebot.types.Message, text: str = None) -> str:
    return env.text.format(
        name=_msg.from_user.first_name + (_msg.from_user.last_name or ''),
        text=text_replace(replace_from_emoji(_msg.text)) if text is None else text
    )


def generate_message_reply(_msg: telebot.types.Message, text: str = None) -> str | None:
    return env.reply_string.format(
        replay_id=_msg.reply_to_message.id,
        replay_msg=text_replace(generate_message(_msg.reply_to_message))
    ) if _msg.reply_to_message.text is not None else text


def check_media(message: telebot.types.Message) -> str:
    if message.sticker is not None:
        return generate_message(
            message,
            env.sticker_string.format(
                sticker_emoji=replace_from_emoji(message.sticker.emoji)
            )
        )
    for i in [
        "video",
        "photo",
        "audio",
        "voice"
    ]:
        if getattr(message, i) is not None:
            return generate_message(message, getattr(env, i + '_string'))
    return ""


async def send_msg_telegram(text: str, thread_id: int) -> bool:
    try:
        await next(bots).send_message(env.chat_id, text, message_thread_id=thread_id)
    except ApiTelegramException as err:
        logging.debug("ApiTelegramException occurred: %s", err)
    else:
        return True
    return False

async def send_message(text: str, message) -> None:
    await js.publish(
        f"tw.econ.write.{message.message_thread_id}",
        text.encode(),
        headers={
            "Nats-Msg-Id": f"{message.from_user.id}_{message.date}_{hash(text)}_{message.chat.id}"
        }
    )


async def message_handler_telegram(message: MsgNats):
    """Takes a message from nats and sends it to telegram."""
    msg = Msg(**json.loads(message.data.decode()))
    logging.debug("tw.%s > %s", msg.message_thread_id, msg.text)

    if buffer.get(msg.message_thread_id) is None:
        buffer[msg.message_thread_id] = Buffer()

    text = f"{msg.name}: {msg.text}" if msg.name is not None and msg.name != "" else f"{msg.text}"

    buffer[msg.message_thread_id].string += text + "\n"
    buffer[msg.message_thread_id].count += 1

    text_hash = hash(text)

    if buffer[msg.message_thread_id].old_message_hash != text_hash or buffer[msg.message_thread_id].count >= env.repetition:
        buffer[msg.message_thread_id].old_message_hash = text_hash

        list_text = [buffer[msg.message_thread_id].string]
        buffer[msg.message_thread_id].count = 0

        if len(buffer[msg.message_thread_id].string) > 4000:
            list_text = split_string(list_text[0], 2000)

        for i in list_text:
            if await send_msg_telegram(i, msg.message_thread_id):
                buffer[msg.message_thread_id].string = ""
    await message.term()


def text_replace(msg: str) -> str:
    return msg.replace("\\", "\\\\").replace("\'", "\\\'").replace("\"", "\\\"").replace("\n", " ")


async def main():
    global js
    nc, js = await nats_connect(env)

    # await js.delete_stream("tw")
    await js.add_stream(name='tw', subjects=['tw.*', 'tw.*.*', 'tw.*.*.*'], max_msgs=5000)
    await js.subscribe("tw.tg.*", "telegram_bot", cb=message_handler_telegram)
    logging.info("nats js subscribe \"tw.tg.*\"")
    logging.info("bot is running")

    await bot.infinity_polling(logger_level=logging.DEBUG)


@bot.message_handler(content_types=["photo", "sticker", "sticker", "audio", "voice"])
async def echo_media(message: telebot.types.Message):
    if js is None or message is None:
        return

    text = ""

    if message.reply_to_message is not None:
        reply = generate_message_reply(message)
        text = f"say \"{reply[:255]}\";" if reply is not None else ""
    text += f"say \"{check_media(message)[:255]}\""

    await send_message(text, message)


@bot.message_handler(content_types=["text"])
async def echo_text(message: telebot.types.Message):
    if js is None or message is None:
        return

    text = ""

    if message.reply_to_message is not None:
        reply = generate_message_reply(message)
        text += f"say \"{reply[:255]}\";" if reply is not None else ""
    text += f"say \"{generate_message(message)[:255]}\""

    await send_message(text, message)


if __name__ == '__main__':
    asyncio.run(main())
