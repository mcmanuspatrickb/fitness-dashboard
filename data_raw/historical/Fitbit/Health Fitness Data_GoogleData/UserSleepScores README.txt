Sleep Scores

The below section is dedicated to the exported data of the Sleep Score data domain.
Sleep scores merge multiple sleep metrics (duration, composition, heart rate data)
into a summarized scoring system.

Files Included:
----------
UserSleepScores.csv

The data for sleep scores
    user_id                                     - the unique identifier of the user
    sleep_id                                    - the unique identifier of the sleep session
    sleep_score_id                              - the unique identifier for the sleep score record

    data_source                                 - the method used to record this stage data (MANUAL, DERIVED, ACTIVELY_MEASURED, PASSIVELY_MEASURED)

    score_utc_offset                            - timezone offset relative to UTC when the score was generated
    score_time                                  - the timestamp (UTC) when the score was generated

    overall_score                               - the calculated overall sleep score

    duration_score                              - sub-score reflecting duration alignment with sleep goals
    composition_score                           - sub-score reflecting the ratio/balance of different sleep stages
    revitalization_score                        - sub-score reflecting how restorative the sleep was (based on e.g. restlessness, HR, etc.)

    sleep_time_minutes                          - total time spent asleep in minutes
    deep_sleep_minutes                          - number of minutes spent in deep sleep
    rem_sleep_percent                           - percentage of total sleep time in the REM stage
    resting_heart_rate                          - measured resting heart rate during sleep
    sleep_goal_minutes                          - the user's sleep goal, in minutes

    waso_count_long_wakes                       - count of longer awakenings
    waso_count_all_wake_time                    - total wake time after initially falling asleep
    restlessness_normalized                     - a normalized measure of restlessness
    hr_below_resting_hr                         - fraction of HR measurements that were below the previous day's resting HR

    sleep_score_created                         - the creation timestamp of the sleep score record in UTC
    sleep_score_last_updated                    - the last update timestamp of the sleep score record in UTC
