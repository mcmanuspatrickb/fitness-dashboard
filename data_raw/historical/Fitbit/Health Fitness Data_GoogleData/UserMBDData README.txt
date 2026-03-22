UserMBDData Export

The User MBD data file contains measured body data including sensitive fields such as is_nursing, pregnant_state, body_constitution etc.

Files included:
----------

UserMBDData.csv

The data for User MBD:

    is_nursing                    - whether the user is nursing
    pregnant_state                - the pregnancy state of the user (not_pregnant, first_trimester etc.)
    body_constitution             - the body constitution of the user (unspecified,regular, lean)
    hr_scaling_sleep_rest         - the user's HR scaling sleep rest
    stride_length_walking         - the user's stride length walking (mm)
    stride_length_running         - the user's stride length running (mm)
    auto_stride_length_walking    - the user's auto stride length walking (mm)
    auto_stride_length_running    - the user's auto stride length running (mm)
    auto_stride_enabled           - whether the user's auto stride is enabled
    auto_run_enabled              - whether the user's auto run is enabled
    activity_state                - the user's activity state (sedentary, low_active, active etc.)
    inactivity_alerts_days        - the user's inactivity alerts days
    sedentary_alert_times         - the user's sedentary alert times
    sedentary_prune_time          - the user's sedentary prune time (UTC, no timezone offset)
    stia_update_time              - the user's STIA update time (UTC, no timezone offset)
    sleep_proc_algorithm          - the user's sleep process algorithm (unspecified, composite, sensitive)
