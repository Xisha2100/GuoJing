"""Load the restricted server environment without evaluating it as shell code."""

import os
import sys

from dotenv import load_dotenv

load_dotenv("/etc/guojing/production.env", override=True)
os.execv(sys.argv[1], sys.argv[1:])
