# Importing necessary libraries
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.common.by import By
from datetime import datetime
import asyncio
import websockets
import base64
import json
import time
import os
import yaml

CONFIG_FILE_PATH = "F:\PROJECT\Steam_Library\PC\config.yaml"

with open(CONFIG_FILE_PATH, 'r') as file:
    config = yaml.safe_load(file)

# Configuration
SERVER_IP = config["server_ip"]
TOKEN_SAVE_PATH = config["token_save_path"]
FIREFOX_PROFILE_PATH = config["firefox_profile_path"]


# Creating Firefox options
firefox_options = Options()

# Adding Firefox profile argument
firefox_options.add_argument("-profile")

# Adding Firefox profile path argument
firefox_options.add_argument(FIREFOX_PROFILE_PATH)

# Async function to send message to WebSocket server
async def send_message(message):
    uri = f"ws://{SERVER_IP}:1234/"  # Replace with your WebSocket server URL
    async with websockets.connect(uri) as websocket:
        await websocket.send(message)
        print(f"Sent: {message}")
    if yaml.safe_load(open(CONFIG_FILE_PATH, 'r'))["shutdown"]:
        os.system("shutdown /s /t 1")

# Async function to get token from Steam
async def get_token():
    # Initializing Firefox driver with options
    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=firefox_options)
    driver.set_window_size(50, 50)
    driver.minimize_window()

    # Getting webpage source
    driver.get("https://store.steampowered.com/pointssummary/ajaxgetasyncconfig")
    rawtab = driver.find_element(By.ID, "rawdata-tab")
    rawtab.click()
    key = driver.page_source

    # Extracting token from source
    key = key[key.index('"webapi_token":"'):key.index("}")-1]
    key = key.replace('"webapi_token":"', '')
    driver.close()

    # Writing token to file
    with open(TOKEN_SAVE_PATH + "token", 'w+') as token_file:
        saved_token = token_file.readline()
        if saved_token != key:
            token_file.write(key)
            coded_string = key.split('.')[1]

            # Decoding token to get expiry time
            key_info = json.loads(base64.b64decode(coded_string + '==').decode('utf-8'))
            with open(TOKEN_SAVE_PATH + "token_exp", "w") as exp_time_file:
                exp_time_file.write(str(key_info['exp']))

            # Sending token to WebSocket server
            await send_message(key)

# Infinite loop to continuously check and update the token
asyncio.run(get_token())

while True:
    # Opening the file containing the expiry time of the token
    with open(TOKEN_SAVE_PATH + "token_exp", "r") as exp_time_file:
        exp_time = exp_time_file.readline()

    # Converting the expiry time to datetime object and adding 60 seconds for buffer
    runtime = datetime.fromtimestamp(float(exp_time) + 60)
    print(f"Next token update scheduled for: {runtime}")

    # Getting the current time
    now = datetime.now()

    # Checking if the current time is past the scheduled token update time
    if now > runtime:
        print("Scheduled token update time has already passed. Updating token immediately...")
        asyncio.run(get_token())
    else:
        # Calculating the wait time until the scheduled token update time
        wait_seconds = (runtime - now).total_seconds()
        print(f"Waiting until {runtime.strftime('%H:%M')} to update the token. That's {wait_seconds} seconds.")
        time.sleep(wait_seconds)
        asyncio.run(get_token())


