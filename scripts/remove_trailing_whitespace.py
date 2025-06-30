import os

def remove_trailing_whitespace():
    """
    Recursively search the src/familybot directory for Python files
    and remove any trailing whitespace from the end of each line.
    """
    for root, _, files in os.walk("src/familybot"):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                updated_lines = [line.rstrip() for line in lines]

                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines("\n".join(updated_lines) + "\n")

                print(f"Removed trailing whitespace from: {file_path}")

if __name__ == "__main__":
    remove_trailing_whitespace()
