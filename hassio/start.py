#!/usr/bin/env python
import sys
import threading

import insteon_mqtt
import webcli

__version__ = insteon_mqtt.__version__

threading.Thread(target=webcli.app.start_webcli, daemon=True).start()
status = insteon_mqtt.cmd_line.main()
sys.exit(status)
