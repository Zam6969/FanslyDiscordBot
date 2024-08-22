import os
import json
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncio

# Define the absolute path to config.json
config_path = 'c:/Users/Zam/Desktop/fans bot/config.json'

def load_config():
    if not os.path.exists(config_path):
        # Create an empty config file if it does not exist
        with open(config_path, 'w') as f:
            json.dump({"token": "", "servers": {}}, f, indent=4)
    with open(config_path, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

config = load_config()

# Extract the bot token from the configuration
BOT_TOKEN = config.get('token')

# Ensure the token is present in the config
if not BOT_TOKEN:
    raise ValueError("Bot token is not set in the configuration.")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
intents.guilds = True  # Enable guilds intent

# Set up the bot
bot = commands.Bot(command_prefix='!', intents=intents)
@bot.event
async def on_disconnect():
    logger.warning("Bot disconnected from Discord")

@bot.event
async def on_resumed():
    logger.info("Bot session resumed successfully")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"An error occurred in event {event}: {args}, {kwargs}")
    
@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    # Sync the commands with Discord
    await bot.tree.sync()
    check_fansly.start()  # Start the periodic check

@bot.tree.command(name="seturl", description="Set a new Fansly URL")
@app_commands.describe(url="The new Fansly URL")
async def set_url(interaction: discord.Interaction, url: str):
    guild_id = str(interaction.guild.id)
    if guild_id not in config["servers"]:
        config["servers"][guild_id] = {}
    config["servers"][guild_id]["fansly_url"] = url
    save_config(config)
    await interaction.response.send_message(f"Fansly URL updated to {url} for this server.")

@bot.tree.command(name="setchannel", description="Set the notification channel")
@app_commands.describe(channel="The Discord channel ID")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    if guild_id not in config["servers"]:
        config["servers"][guild_id] = {}
    config["servers"][guild_id]["channel_id"] = channel.id
    save_config(config)
    await interaction.response.send_message(f"Notification channel set to {channel.mention} for this server.")

@bot.tree.command(name="setmessage", description="Set the notification message")
@app_commands.describe(message="The new notification message")
async def set_message(interaction: discord.Interaction, message: str):
    guild_id = str(interaction.guild.id)
    if guild_id not in config["servers"]:
        config["servers"][guild_id] = {}
    config["servers"][guild_id]["notification_message"] = message
    save_config(config)
    await interaction.response.send_message(f"Notification message updated to: {message}")

@bot.tree.command(name="ping", description="Check if the bot is responsive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

@tasks.loop(seconds=120)
async def check_fansly():
    for guild_id, settings in config["servers"].items():
        fansly_url = settings.get("fansly_url")
        channel_id = settings.get("channel_id")
        notification_message = settings.get("notification_message", "ONLINE NOW JOIN EVERYONE WTF")

        if not fansly_url or not channel_id:
            logger.info(f"No Fansly URL or channel ID set for server {guild_id}. Skipping check.")
            continue  # Skip if no URL or channel is provided

        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode (no browser window)

        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            driver.implicitly_wait(5)  # Short implicit wait

            # Open the URL
            driver.get(fansly_url)

            # Wait for the age gate popup to appear and then click the button to close it
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "/html/body/app-root/div/div[3]/app-age-gate-modal/div/div/div[4]/div/div[2]"))
                )
                age_gate_button = driver.find_element(By.XPATH, "/html/body/app-root/div/div[3]/app-age-gate-modal/div/div/div[4]/div/div[2]")
                age_gate_button.click()
            except NoSuchElementException:
                logger.info("Age gate button not found or already closed.")

            # Wait for the content to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, '//video[@src]'))
                )
                # If we reach this point, the video element is visible
                if settings.get("notification_message_id") is None:
                    await send_online_notification(guild_id, channel_id, notification_message)
            except TimeoutException:
                logger.info("No Video Found Creator Offline")
                if settings.get("notification_message_id") is not None:
                    await delete_notification_message(guild_id, channel_id)

        except Exception as e:
            logger.error(f"Error during Fansly check for server {guild_id}: {e}")

        finally:
            driver.quit()

async def send_online_notification(guild_id, channel_id, message):
    channel = bot.get_channel(channel_id)
    if channel:
        msg = await channel.send(message)
        config["servers"][guild_id]["notification_message_id"] = msg.id
        save_config(config)
        logger.info(f"Sent online notification to server {guild_id}.")

async def delete_notification_message(guild_id, channel_id):
    channel = bot.get_channel(channel_id)
    if channel and config["servers"][guild_id].get("notification_message_id"):
        try:
            message = await channel.fetch_message(config["servers"][guild_id]["notification_message_id"])
            await message.delete()
            logger.info(f"Deleted previous online notification for server {guild_id}.")
        except discord.NotFound:
            logger.warning(f"Notification message not found for server {guild_id}.")
        config["servers"][guild_id]["notification_message_id"] = None
        save_config(config)

bot.run(BOT_TOKEN)
