from motor.motor_asyncio import AsyncIOMotorClient

import config

client = AsyncIOMotorClient(config.MONGO_URL)
db = client[config.DB_NAME]

runs = db.review_runs
policies = db.security_policies
deliveries = db.webhook_deliveries


async def ensure_indexes():
    await runs.create_index("id", unique=True)
    await runs.create_index([("created_at", -1)])
    await policies.create_index("id", unique=True)
    await deliveries.create_index("delivery_id", unique=True)
