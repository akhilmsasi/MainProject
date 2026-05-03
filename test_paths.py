import os

# 1. Print where the script thinks it is
print(f"Current Working Directory: {os.getcwd()}")

# 2. List all files in the current directory
print("\nFiles in this folder:")
for file in os.listdir("."):
    print(f"- {file}")

# 3. Check if your target folder exists at all
target_dir = r"C:\Users\ASHNA\Documents\Ashna\Project Report\ProjectWork\Backend_code"
print(f"\nDoes the 'Backend_code' folder exist? {os.path.exists(target_dir)}")