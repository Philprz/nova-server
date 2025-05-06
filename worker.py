import asyncio
from aio_pika import connect_robust, ExchangeType
import json
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logging.info("🛠️  Worker démarré, tentative de connexion à RabbitMQ…")


async def main():
    conn = await connect_robust("amqp://guest:guest@localhost/")
    channel = await conn.channel()
    exchange = await channel.declare_exchange("nova.exchange", ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue("quote_queue", durable=True)
    await queue.bind(exchange, routing_key="quote.create")

    async with queue.iterator() as it:
        async for message in it:
            async with message.process():
                payload = json.loads(message.body)
                # → ici orchestration LLM / SAP / Salesforce
                # → puis éventuelle publication du résultat sur une autre queue ou webhook
if __name__ == "__main__":
    asyncio.run(main())
