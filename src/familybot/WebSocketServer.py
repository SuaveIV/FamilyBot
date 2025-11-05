# In src/familybot/WebSocketServer.py

import asyncio
import base64
import json
import logging
import os  # For os.path.join

import websockets

from familybot.config import (  # Import PROJECT_ROOT for token file paths
    IP_ADDRESS,
    PROJECT_ROOT,
)

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

# Define token file paths relative to PROJECT_ROOT
TOKEN_SAVE_DIR = os.path.join(PROJECT_ROOT, "tokens")
TOKEN_FILE_PATH = os.path.join(TOKEN_SAVE_DIR, "token")
TOKEN_EXP_FILE_PATH = os.path.join(TOKEN_SAVE_DIR, "token_exp")

# Ensure the token save directory exists
try:
    os.makedirs(TOKEN_SAVE_DIR, exist_ok=True)
    logger.info(f"Ensured token directory exists: {TOKEN_SAVE_DIR}")
except Exception as e:
    logger.critical(f"Failed to create token directory {TOKEN_SAVE_DIR}: {e}")
    # Consider exiting or raising a more specific error if this is fatal
    # For now, let it proceed, but file operations will likely fail.


# Async function to handle WebSocket communication
async def handle_websocket(websocket, path):
    logger.info(f"Client connected from {websocket.remote_address} on path: {path}")
    try:
        # Continuously listen for new messages from the WebSocket
        async for message in websocket:
            logger.info(
                f"Received message from {websocket.remote_address}: {message[:50]}..."
            )  # Log first 50 chars of message

            # Write the new token to a file
            try:
                with open(TOKEN_FILE_PATH, "w") as token_file:
                    token_file.write(message)
                logger.info(f"Token successfully written to file: {TOKEN_FILE_PATH}.")
            except IOError as e:
                logger.error(f"Error writing token to file {TOKEN_FILE_PATH}: {e}")

            # Decode and load the token to extract expiration timestamp
            try:
                # Add padding if necessary for base64 decoding (JWT specific)
                padded_token_part = (
                    message.split(".")[1].replace("-", "+").replace("_", "/")
                )
                padded_token_part += "=" * (-len(padded_token_part) % 4)

                key_info = json.loads(
                    base64.b64decode(padded_token_part).decode("utf-8")
                )
                exp_timestamp = key_info["exp"]

                # Write the expiration timestamp to a file
                with open(TOKEN_EXP_FILE_PATH, "w") as exp_file:
                    exp_file.write(str(exp_timestamp))
                logger.info(
                    f"Expiration timestamp {exp_timestamp} written to file: {TOKEN_EXP_FILE_PATH}."
                )
            except (IndexError, json.JSONDecodeError, base64.binascii.Error) as e:
                logger.error(
                    f"Error decoding or parsing token: {e}. Raw message start: {message[:100]}"
                )
            except IOError as e:
                logger.error(
                    f"Error writing token expiration to file {TOKEN_EXP_FILE_PATH}: {e}"
                )

    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"Client {websocket.remote_address} disconnected normally.")
    except websockets.exceptions.ConnectionClosedError as e:
        logger.warning(
            f"Client {websocket.remote_address} disconnected with error: {e}"
        )
    except asyncio.CancelledError:
        logger.info(f"WebSocket handler for {websocket.remote_address} cancelled.")
    except Exception as e:
        logger.critical(
            f"Unexpected error in handle_websocket for {websocket.remote_address}: {e}",
            exc_info=True,
        )
    finally:
        logger.info(f"Connection to {websocket.remote_address} closed.")


# Async function to start the WebSocket server
async def start_websocket_server_task():
    logger.info(f"Attempting to start WebSocket server on ws://{IP_ADDRESS}:1234")
    server = None  # Initialize server
    try:
        server = await websockets.serve(handle_websocket, IP_ADDRESS, 1234)
        logger.info("WebSocket server started successfully. Running indefinitely.")
        await server.serve_forever()  # This allows it to be cancelled
    except asyncio.CancelledError:
        logger.info("WebSocket server task cancelled. Shutting down...")
    except Exception as e:
        logger.critical(f"Failed to start or run WebSocket server: {e}", exc_info=True)
    finally:
        if server:
            server.close()  # Close the server listener
            await server.wait_closed()  # Wait for it to fully close
            logger.info("WebSocket server closed.")


# No asyncio.run() call here, as it's run as a task by FamilyBot.py
