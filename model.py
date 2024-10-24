from typing import Optional, Union

from pydantic import BaseModel, Field


class Env(BaseModel):
    TELEGRAM_BOT_TOKENS: str | list = None
    chat_id: str = None
    nats_server: str = Field("127.0.0.1")
    nats_user: str = None
    nats_password: str = None
    log_level: str = Field("info")
    text: str = Field("[TG] {name}: {text}")
    sticker_string: str = Field("[STICKER {sticker_emoji}]")
    video_string: str = Field("[MEDIA]")
    photo_string: str = Field("[PHOTO]")
    audio_string: str = Field("[AUDIO]")
    voice_string: str = Field("[VOICE]")
    reply_string: str = Field("[Reply {replay_id}] {replay_msg}")
    repetition: int = Field(100)


class Msg(BaseModel):
    server_name: Optional[str]
    name: Optional[str]
    message_thread_id: Union[int, str]
    regex_type: str
    text: Optional[str]


class Buffer(BaseModel):
    string: str = Field("")
    old_message_hash: int = Field(0)
    count: int = Field(0)
