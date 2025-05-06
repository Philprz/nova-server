from simple_salesforce import Salesforce
import os
from dotenv import load_dotenv

load_dotenv()

sf = Salesforce(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    domain=os.getenv("SALESFORCE_DOMAIN", "login")
)

result = sf.query("SELECT Id, Name FROM Account LIMIT 1")
print(result)
