import discord
import requests
import os
import base64
from discord.ext import tasks, commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# WooCommerce API credentials from .env file
wc_api_url = os.getenv("WC_API_URL")
wc_consumer_key = os.getenv("WC_CONSUMER_KEY")
wc_consumer_secret = os.getenv("WC_CONSUMER_SECRET")

# Create the Basic Authentication header
credentials = f"{wc_consumer_key}:{wc_consumer_secret}"
b64_credentials = base64.b64encode(credentials.encode()).decode()
headers = {
    "Authorization": f"Basic {b64_credentials}"
}

# Discord Bot token and channel ID from .env file
discord_token = os.getenv("DISCORD_TOKEN")
channel_id = int(os.getenv("CHANNEL_ID"))

# WooCommerce store base URL (without trailing slash)
wc_store_url = os.getenv("WC_STORE_URL")

# Initialize the bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionary to track stock status
previous_stock = {}

# Function to get product categories as a comma-separated string
def get_categories(product):
    categories = product.get("categories", [])
    return ", ".join([category["name"] for category in categories])

# Function to check product stock status with pagination
def check_stock():
    page = 1
    per_page = 100  # Number of products per page, can adjust as needed
    stock_status = {}

    while True:
        response = requests.get(
            f"{wc_api_url}?per_page={per_page}&page={page}", headers=headers
        )

        try:
            products = response.json()

            if isinstance(products, dict) and products.get("code"):
                print(f"API Error: {products.get('message')}")
                break

            if not isinstance(products, list):
                print("Unexpected response structure: not a list of products.")
                break

            # Process products and add to stock_status dictionary
            for product in products:
                stock_status[product.get("id")] = {
                    "name": product.get("name"),
                    "status": "In Stock" if product.get("stock_status") == "instock" else "Out of Stock",
                    "categories": get_categories(product),
                    "url": product.get("permalink")  # Get the product URL
                }

            # If fewer products are returned than per_page, it means we've reached the last page
            if len(products) < per_page:
                break

            page += 1

        except ValueError:
            print("Failed to parse response as JSON.")
            break

    return stock_status

# Background task that runs every 60 minutes
@tasks.loop(minutes=60)
async def stock_monitor():
    global previous_stock
    channel = bot.get_channel(channel_id)
    current_stock = check_stock()

    # Compare current stock status with previous stock status
    for product_id, info in current_stock.items():
        previous_info = previous_stock.get(product_id)

        if previous_info is None:
            # New product, add it to the previous stock
            previous_stock[product_id] = info
            continue

        if info["status"] != previous_info["status"]:
            if info["status"] == "In Stock":
                # Notify if product is back in stock
                product_name = info["name"]
                product_categories = info["categories"]
                product_url = f"<{info['url']}>"
                message = f"🚨 **The following product is back in stock:**\n{product_name} ({product_categories})\n{product_url}"
                await channel.send(message)
            # Update the previous status
            previous_stock[product_id] = info

    # Optionally handle products that were previously in stock but are now out of stock
    for product_id in list(previous_stock.keys()):
        if product_id not in current_stock:
            del previous_stock[product_id]

# Event triggered when the bot is ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # List stock status in the console when the bot starts
    initial_stock = check_stock()
    if initial_stock:
        print("📉 **Initial stock status:**")
        for product_id, info in initial_stock.items():
            print(f"Product {info['name']} ({info['categories']}) is {info['status']}")
    else:
        print("No products found or unable to fetch stock status.")

    previous_stock.update(initial_stock)
    stock_monitor.start()

# Start the bot
bot.run(discord_token)
