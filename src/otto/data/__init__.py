import logging
import os

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.data')
logger.addHandler(logging.NullHandler())
