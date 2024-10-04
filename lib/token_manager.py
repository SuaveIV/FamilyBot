from datetime import datetime
import subprocess
from config import *

COMMAND = ["python", SCRIPT_PATH + "//WebSocketServer.py"]
# Function to check if token is expired
def check_token_exp() -> bool:
    now = datetime.now()
    now = int(now.timestamp())
    token_exp_file = open(SCRIPT_PATH + "/token_Exp", "r")
    token_exp = token_exp_file.readline()
    token_exp_file.close()
    if now > int(token_exp):
        return False
    else:
        return True
    
def start_webSocket_Server() -> None:    
    global process 
    process = subprocess.Popen(COMMAND)
    print("WebSocket server Started")
    
async def restart_ws_server()-> None:
    global process
    # Kill the subprocess if it's running
    if process is not None:
        process.kill()
    # Start the WebSocketServer as a subprocess
    process = subprocess.Popen(COMMAND)
    print("WebSocket server Restarted")
    
def get_token() ->str:
    token_file = open(SCRIPT_PATH + "/token", "r")
    token = token_file.readline()
    token_file.close()
    return token