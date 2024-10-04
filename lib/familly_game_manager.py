from config import *

# Function to get saved games from file
def get_saved_games() -> list:
    game_file = open(SCRIPT_PATH + '/gamelist.txt', 'r')
    game_file_list = game_file.readlines()
    game_file.close()
    i = 0
    for game in game_file_list:
        game_file_list[i] = game.replace('\n', "")
        i += 1
    return game_file_list

# Function to set saved games in file
def set_saved_games(game_list: list) -> None:
    with open(SCRIPT_PATH + '/gamelist.txt', 'w') as save_file:
        save_file.write('\n'.join(str(i) for i in game_list))