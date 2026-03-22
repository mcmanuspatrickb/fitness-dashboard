EcgAppEvents.json

This file contains events logged by your Fitbit device's ECG app.
Each entry is a JSON object that includes a mandatory "func_addr" and "line_no" fields, plus exactly one of the following:
  - error
  - view_changed
  - button_pressed
  - analyze_result
  - duration
  - deleted_result
  - heap_info
