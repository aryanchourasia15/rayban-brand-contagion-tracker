"""Community Cloud entry point: always synthetic, regardless of environment settings."""
from app import main

main(cloud=True)
