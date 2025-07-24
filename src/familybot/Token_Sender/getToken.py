# In src/familybot/Token_Sender/getToken.py

# Importing necessary libraries
import asyncio
import base64
import json
import os
import signal  # For graceful shutdown
import sys  # For graceful shutdown
from datetime import datetime
from pathlib import Path
import binascii  # Added for base64 error handling

import websockets
from websockets.exceptions import ConnectionRefusedError, WebSocketException
import yaml
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

# Add the src directory to the Python path for logging imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import enhanced logging configuration
from familybot.lib.logging_config import setup_script_logging

# Setup enhanced logging for this script
logger = setup_script_logging("token_sender", "INFO")

# --- CONFIG_FILE_PATH logic ---
# Use Path(__file__).parent to get the directory of the current script (getToken.py)
# Assuming config.yaml for the token bot is in the same folder as getToken.py
CONFIG_FILE_PATH = Path(__file__).parent / "config.yaml"

try:
    with open(CONFIG_FILE_PATH, 'r') as file:
        config = yaml.safe_load(file)
except FileNotFoundError:
    logger.critical(f"Config file not found at {CONFIG_FILE_PATH}. Please ensure it exists.")
    sys.exit(1)
except yaml.YAMLError as e:
    logger.critical(f"Error parsing config.yaml: {e}")
    sys.exit(1)

# Configuration
SERVER_IP = config.get("server_ip")
TOKEN_SAVE_PATH = config.get("token_save_path") # This should be a path relative to project root
FIREFOX_PROFILE_PATH = config.get("firefox_profile_path")
SHUTDOWN_ON_SEND = config.get("shutdown", False)

# Basic validation of config
if not all([SERVER_IP, TOKEN_SAVE_PATH, FIREFOX_PROFILE_PATH]):
    logger.critical("Missing essential configuration parameters in Token_Sender/config.yaml. Please check server_ip, token_save_path, and firefox_profile_path.")
    sys.exit(1)

# Ensure TOKEN_SAVE_PATH is relative to the PROJECT_ROOT
# Need to import PROJECT_ROOT from familybot.config to be truly robust if TOKEN_SAVE_PATH is relative to project root
# For now, let's assume TOKEN_SAVE_PATH is relative to where getToken.py is run *from* (i.e., FamilyBot/ root)
# If TOKEN_SAVE_PATH in config.yaml is "tokens/", then this will be "FamilyBot/tokens/"
# If TOKEN_SAVE_PATH is meant to be relative to getToken.py's location, then adjust here.
# For simplicity and consistency with other files, let's assume it's relative to PROJECT_ROOT
try:
    from familybot.config import \
        PROJECT_ROOT  # Import PROJECT_ROOT from main config
    ACTUAL_TOKEN_SAVE_DIR = os.path.join(PROJECT_ROOT, TOKEN_SAVE_PATH)
except ImportError:
    logger.warning("Could not import PROJECT_ROOT from familybot.config. Assuming TOKEN_SAVE_PATH is absolute or relative to current working directory.")
    ACTUAL_TOKEN_SAVE_DIR = TOKEN_SAVE_PATH # Fallback if PROJECT_ROOT is not found/used

# Ensure the token save path directory exists
try:
    os.makedirs(ACTUAL_TOKEN_SAVE_DIR, exist_ok=True)
    logger.info(f"Ensured token save directory exists: {ACTUAL_TOKEN_SAVE_DIR}")
except Exception as e:
    logger.critical(f"Failed to create token save directory {ACTUAL_TOKEN_SAVE_DIR}: {e}")
    sys.exit(1)


# Creating Firefox options
firefox_options = Options()
firefox_options.add_argument("-profile")
firefox_options.add_argument(FIREFOX_PROFILE_PATH)

# --- Graceful Shutdown Flag ---
_shutdown_requested = asyncio.Event()

# --- Signal Handler ---
def signal_handler(sig, frame):
    logger.info(f"Caught signal {sig.name}. Setting shutdown flag...")
    _shutdown_requested.set() # Set the event to signal shutdown

# Async function to send message to WebSocket server
async def send_message(message: str):
    uri = f"ws://{SERVER_IP}:1234/"
    try:
        async with websockets.connect(uri, open_timeout=5) as websocket: # Added open_timeout
            await websocket.send(message)
            logger.info(f"Sent token to WebSocket server: {message[:20]}...")
    except ConnectionRefusedError:
        logger.error(f"WebSocket connection refused to {uri}. Is the server running? Retrying later...")
    except WebSocketException as e: # Catch other websocket related errors
        logger.error(f"WebSocket error sending message to {uri}: {e}")
    except asyncio.TimeoutError:
        logger.error(f"Timed out trying to connect to WebSocket server at {uri}.")
    except Exception as e:
        logger.error(f"Unexpected error sending message to WebSocket server: {e}")

    if SHUTDOWN_ON_SEND:
        logger.info("Shutdown enabled in config. Shutting down system.")
        os.system("shutdown /s /t 1") # This will only run on Windows

# Async function to get token from Steam
async def get_token():
    logger.info("Starting get_token process using Selenium...")
    driver = None
    try:
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=firefox_options)
        driver.set_window_size(50, 50)
        # minimize_window() might not work consistently on all OS/setups, or needs focus
        try:
            driver.minimize_window()
        except Exception as e:
            logger.debug(f"Could not minimize window: {e}. Continuing...")


        driver.get("https://store.steampowered.com/pointssummary/ajaxgetasyncconfig")
        await asyncio.sleep(3) # Give page time to load and JS to execute

        key = driver.page_source

        # Check if rawdata-tab exists before clicking or if the data is already accessible
        try:
            rawtab = driver.find_element(By.ID, "rawdata-tab")
            rawtab.click()
            await asyncio.sleep(1) # Wait for tab content to load
            key = driver.page_source # Get updated page source after click
        except Exception as e:
            logger.warning(f"Could not click rawdata-tab (might not exist or be visible, or page changed): {e}")
            # Assume key is already in initial page source or will be found later if this is just a warning.

        start_token_marker = '"webapi_token":"'
        end_token_marker = '"}'

        start_index = key.find(start_token_marker)
        if start_index == -1:
            logger.error("Could not find 'webapi_token' start marker in page source.")
            return # Exit if token not found

        key_start = start_index + len(start_token_marker)
        key_end = key.find(end_token_marker, key_start)
        if key_end == -1:
            logger.error("Could not find 'webapi_token' end marker in page source.")
            return # Exit if end not found

        extracted_key = key[key_start:key_end]

        if not extracted_key:
            logger.error("Extracted token is empty. Page source might have changed or extraction logic is flawed.")
            return

        logger.info(f"Extracted key: {extracted_key[:20]}...")

        # Read saved token for comparison
        saved_token = ""
        try:
            with open(os.path.join(ACTUAL_TOKEN_SAVE_DIR, "token"), 'r') as token_file:
                saved_token = token_file.readline().strip()
        except FileNotFoundError:
            logger.info(f"Existing token file not found at {os.path.join(ACTUAL_TOKEN_SAVE_DIR, 'token')}. Will create new.")
        except Exception as e:
            logger.error(f"Error reading existing token file: {e}")

        # Check if token has changed
        if saved_token != extracted_key:
            logger.info("New token found! Writing to file and sending to server.")
            # Writing new token to file
            with open(os.path.join(ACTUAL_TOKEN_SAVE_DIR, "token"), 'w') as token_file:
                token_file.write(extracted_key)

            # Decoding token to get expiry time
            try:
                coded_string = extracted_key.split('.')[1]
                # Pad and replace URL-safe chars for base64 decoding
                padded_coded_string = coded_string.replace('-', '+').replace('_', '/')
                padded_coded_string += '=' * (-len(padded_coded_string) % 4)

                key_info = json.loads(base64.b64decode(padded_coded_string).decode('utf-8'))
                exp_timestamp = key_info['exp']

                # Writing expiry time to file
                with open(os.path.join(ACTUAL_TOKEN_SAVE_DIR, "token_exp"), "w") as exp_time_file:
                    exp_time_file.write(str(exp_timestamp))
                logger.info(f"Expiration timestamp {exp_timestamp} saved.")

                # Sending token to WebSocket server
                await send_message(extracted_key)
            except (IndexError, json.JSONDecodeError, binascii.Error) as e:  # Fixed import path
                logger.error(f"Error decoding or parsing new token: {e}. Raw extracted key: {extracted_key[:100]}")
            except IOError as e:
                logger.error(f"Error writing new token/exp_time to file: {e}")
        else:
            logger.info("Token has not changed. No update needed.")

    except Exception as e:
        logger.error(f"An error occurred during get_token: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logger.info("Firefox driver closed.")


# Main async loop for scheduling token updates
async def token_update_scheduler():
    logger.info("Starting token update scheduler...")

    while not _shutdown_requested.is_set():
        try:
            await get_token()

            exp_time = None
            token_exp_file_path = os.path.join(ACTUAL_TOKEN_SAVE_DIR, "token_exp")
            try:
                with open(token_exp_file_path, "r") as exp_time_file:
                    exp_time_str = exp_time_file.readline().strip()
                    if exp_time_str:
                        exp_time = float(exp_time_str)
                    else:
                        logger.warning(f"Token expiration file '{token_exp_file_path}' is empty. Fetching token again soon.")
                        await asyncio.wait_for(_shutdown_requested.wait(), timeout=300) # Wait 5 mins or until shutdown
                        continue
            except FileNotFoundError:
                logger.warning(f"Token expiration file '{token_exp_file_path}' not found. Fetching token again soon.")
                await asyncio.wait_for(_shutdown_requested.wait(), timeout=300)
                continue
            except ValueError:
                logger.error(f"Invalid expiration time in '{token_exp_file_path}': '{exp_time_str}'. Fetching token again soon.")
                await asyncio.wait_for(_shutdown_requested.wait(), timeout=300)
                continue
            except Exception as e:
                logger.error(f"Error reading token expiration file: {e}. Fetching token again soon.")
                await asyncio.wait_for(_shutdown_requested.wait(), timeout=300)
                continue

            # Calculate runtime: expiry time - buffer (e.g., 1 hour before expiry)
            # Steam API tokens are typically short-lived (e.g., 1 hour).
            # Fetching 5-10 minutes before expiry is safer.
            BUFFER_SECONDS = 5 * 60 # Update 5 minutes before expiry
            runtime = datetime.fromtimestamp(exp_time - BUFFER_SECONDS)

            now = datetime.now()
            logger.info(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Token expires at: {datetime.fromtimestamp(exp_time).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Next update scheduled for: {runtime.strftime('%Y-%m-%d %H:%M:%S')}")

            if now >= runtime:
                logger.info("Scheduled token update time has already passed or is imminent. Updating token immediately...")
                # No sleep needed here, loop will restart immediately
            else:
                wait_seconds = (runtime - now).total_seconds()
                logger.info(f"Waiting for {int(wait_seconds)} seconds until next update.")
                await asyncio.wait_for(_shutdown_requested.wait(), timeout=wait_seconds)

        except asyncio.TimeoutError:
            logger.debug("Sleep period completed, fetching new token.")
        except asyncio.CancelledError:
            logger.info("Token update scheduler cancelled.")
            break
        except Exception as e:
            logger.critical(f"An unexpected error occurred in token_update_scheduler main loop: {e}", exc_info=True)
            await asyncio.wait_for(_shutdown_requested.wait(), timeout=60) # Wait a minute before retrying after error

    logger.info("Token update scheduler has shut down gracefully.")

# Entry point for the script
if __name__ == "__main__":
    # Register Ctrl+C handler for Windows before running the loop
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(token_update_scheduler())
    except KeyboardInterrupt:
        logger.info("Script terminated by user (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Unhandled exception during asyncio.run: {e}", exc_info=True)
