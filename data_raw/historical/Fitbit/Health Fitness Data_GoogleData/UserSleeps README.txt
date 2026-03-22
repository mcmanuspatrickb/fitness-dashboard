Sleeps

The below section is dedicated to the exported data of the Sleep data domain.
Sleeps are sent by the wearable device (or manually entered) and contain data about
the user's sleep sessions.

Files Included:
----------
UserSleeps.csv

The data for sleeps
    user_id                                     - the unique identifier of the user
    sleep_id                                    - the unique identifier of the sleep session
    sleep_type                                  - the type of the sleep session (CLASSIC, STAGES)

    minutes_in_sleep_period                     - the total number of minutes between going to bed and final wake-up
    minutes_after_wake_up                       - total minutes after the user wakes up until they leave bed or stop tracking
    minutes_to_fall_asleep                      - number of minutes it took the user to fall asleep
    minutes_asleep                              - the total number of minutes the user was actually asleep
    minutes_awake                               - the total number of minutes awake during the sleep session
    minutes_longest_awakening                   - duration (in minutes) of the single longest awakening
    minutes_to_persistent_sleep                 - number of minutes between going to bed and the onset of sustained sleep

    start_utc_offset                            - timezone offset relative to UTC at the start of the sleep
    sleep_start                                 - the start time of the sleep session in UTC

    end_utc_offset                              - timezone offset relative to UTC at the end of the sleep
    sleep_end                                   - the end time of the sleep session in UTC

    data_source                                 - the method used to record this sleep (MANUAL, DERIVED, ACTIVELY_MEASURED, PASSIVELY_MEASURED)

    sleep_created                               - the creation timestamp of the sleep record in UTC
    sleep_last_updated                          - the last update timestamp of the sleep record in UTC
