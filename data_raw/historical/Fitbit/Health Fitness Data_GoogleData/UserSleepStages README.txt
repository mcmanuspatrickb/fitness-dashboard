Sleep Stages

The below section is dedicated to the exported data of the Sleep Stage data domain.
Sleep stage data gives more detailed insight into how a user's sleep is distributed
across different stages.

Files Included:
----------
UserSleepStages.csv

The data for sleep stages
    user_id                                     - the unique identifier of the user
    sleep_id                                    - the unique identifier of the sleep session
    sleep_stage_id                              - the unique identifier of the sleep stage entry
    sleep_stage_type                            - the type of sleep stage (AWAKE, LIGHT, DEEP, REM)

    start_utc_offset                            - timezone offset relative to UTC at the start of this sleep stage
    sleep_stage_start                           - the start time of this sleep stage in UTC

    end_utc_offset                              - timezone offset relative to UTC at the end of this sleep stage
    sleep_stage_end                             - the end time of this sleep stage in UTC

    data_source                                 - the method used to record this stage data (MANUAL, DERIVED, ACTIVELY_MEASURED, PASSIVELY_MEASURED)

    sleep_stage_created                         - the creation timestamp of the sleep stage record in UTC
    sleep_stage_last_updated                    - the last update timestamp of the sleep stage record in UTC
