import os

print("Running Pylint remediation script...")

# Reorder imports
os.system("uv run python -m isort .")
print("Imports reordered successfully.")

# Add final newlines
python_files = [
    f
    for f in os.listdir("src/familybot")
    if f.endswith(".py") and not f.endswith("__init__.py")
]
for file in python_files:
    with open(os.path.join("src", "familybot", file), "a", encoding="utf-8") as f:
        f.write("\n")
print("Missing final newlines added successfully.")

print("Pylint remediation script complete.")
