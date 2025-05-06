import asyncio
from aio_pika import connect_robust, Message, ExchangeType
import json

RABBIT_URL = "amqp://guest:guest@localhost/"

async def get_connection():
    return await connect_robust(RABBIT_URL)

async def publish_create_quote(payload: dict):
    conn = await get_connection()
    channel = await conn.channel()
    exchange = await channel.declare_exchange("nova.exchange", ExchangeType.TOPIC, durable=True)
    message = Message(body=json.dumps(payload).encode(), delivery_mode=2)
    await exchange.publish(message, routing_key="quote.create")
    await conn.close()
