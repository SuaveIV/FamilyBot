# Importing necessary libraries
import asyncio
import websockets
import base64
import json
from config import *

# Setting up logging configuration
LOG_FORMAT = '%(asctime)s %(message)s'

# Async function to handle WebSocket communication
async def handle_websocket(websocket, path):
    global token
    # Continuously listen for new messages from the WebSocket
    async for message in websocket:
        # Log the received message

        # Update the token with the received message
        token = message

        # Write the new token to a file
        with open(SCRIPT_PATH + "/token", "w") as token_file:
            token_file.write(token)
        # Decode and load the token to extract expiration timestamp
        key_info = json.loads(base64.b64decode(token.split('.')[1] + '==').decode('utf-8'))
        exp_timestamp = key_info['exp']

        # Write the expiration timestamp to a file
        with open(SCRIPT_PATH + "/tokenExp", "w") as exp_file:
            exp_file.write(str(exp_timestamp))
# Async function to start the WebSocket server
async def start_websocket_server():

    # Create a WebSocket server and run it indefinitely
    async with websockets.serve(handle_websocket, IP_ADDRESS, 1234):
        await asyncio.Future()  # run forever
        
# Run the WebSocket server
asyncio.run(start_websocket_server())
