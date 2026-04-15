import logging

from warden.configs import Configs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

Configs.load_configs()
