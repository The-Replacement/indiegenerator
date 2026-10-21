"""The bus effects: a short reverb and the station's dotted-eighth delay.

Both carry their state as a value: coefficients in, audio and new state out.
The delay lines are realised block by block, so the filtering runs at the
speed of the array and a block-wise render is identical to a single-shot one.
"""

from __future__ import annotations

from indiegen.fx.delay import DelayState as DelayState
from indiegen.fx.delay import delay_state as delay_state
from indiegen.fx.delay import render_delay as render_delay
from indiegen.fx.reverb import ReverbState as ReverbState
from indiegen.fx.reverb import render_reverb as render_reverb
from indiegen.fx.reverb import reverb_state as reverb_state
