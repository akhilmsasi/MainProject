import os
import sys
import subprocess

def install_requirements():
    setup_dir = os.path.dirname(os.path.abspath(__file__))
    requirements_file = os.path.join(setup_dir, 'requirements.txt')
    
    if not os.path.exists(requirements_file):
        print(f"Error: {requirements_file} not found.")
        sys.exit(1)
        
    print(f"Installing requirements from {requirements_file}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
        print("\nAll dependencies installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"\nError occurred while installing dependencies: {e}")
        sys.exit(1)

if __name__ == "__main__":
    install_requirements()