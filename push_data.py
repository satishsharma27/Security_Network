import os
from pymongo import MongoClient
uri = os.getenv("MONGO_DB_URL")
client = MongoClient(uri)
try:
    client.admin.command("ping")
    print("Connected successfully")
    client.close()

except Exception as e:
    raise Exception(
        "The following error occurred: ", e)