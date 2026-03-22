Exercises

The below section is dedicated to the exported data of the Exercise data domain.
Exercises are sent by the wearables device to the Backend and contain data about
the exercises performed by the user.

Files Included:
----------

UserExercises.csv

The data for exercises
    exercise_id                                     - the unique identifier of the exercise
    exercise_start                                  - the exercise start time at UTC
    exercise_end                                    - the exercise end time at UTC
    utc_offset                                      - the timezone offset relative to UTC for the exercise
    exercise_created                                - the time when the exercise was created at UTC
    exercise_last_updated                           - the time when the exercise was last updated at UTC
    activity_name                                   - the type of activity performed during the exercise
    log_type                                        - where the exercise was logged from (mobile, tracker, etc.)

    pool_length                                     - user's preferred pool length in the unit specified by PoolLengthUnit
    pool_length_unit                                - pool length unit

    intervals                                       data about the intervals of the exercise (if the exercise was an interval workout).
                                                    it is listed as blocks of the following -
                                                    - type: the type of the interval (REST or MOVE)
                                                    - interval_num: the interval number
                                                    - total_intervals: the total number of intervals in the workout
                                                    - num_repeats: the number of times the interval was repeated
                                                    - duration_millis: the interval duration in milliseconds

    distance_units                                  - the units of the distance (imperial or metric)
    tracker_total_calories                          - the total calories burned during the exercise (registered by the tracker)
    tracker_total_steps                             - the total steps taken during the exercise (registered by the tracker)
    tracker_total_distance_mm                       - the total distance in millimeters covered during the exercise (registered by the tracker)
    tracker_total_altitude_mm                       - the total altitude in millimeters covered during the exercise (registered by the tracker)
    tracker_avg_heart_rate                          - the average heart rate during the exercise (registered by the tracker)
    tracker_peak_heart_rate                         - the peak heart rate during the exercise (registered by the tracker)
    tracker_avg_pace_mm_per_second                  - the average pace in millimeters per second during the exercise (registered by the tracker)
    tracker_avg_speed_mm_per_second                 - the average speed in millimeters per second during the exercise (registered by the tracker)
    tracker_peak_speed_mm_per_second                - the peak speed in millimeters per second during the exercise (registered by the tracker)
    tracker_auto_stride_run_mm                      - the stride length when running in millimeters during the exercise (registered by the tracker)
    tracker_auto_stride_walk_mm                     - the stride length when walking in millimeters during the exercise (registered by the tracker)
    tracker_swim_lengths                            - the number of lengths swam during a swim exercise (registered by the tracker)
    tracker_pool_length                             - the pool length in the unit specified by TrackerPoolLengthUnit (calculated by the tracker)
    tracker_pool_length_unit                        - the pool length unit
    tracker_cardio_load                             - the cardio load of the exercise (registered by the tracker)

    manually_logged_total_calories                  - total calories burned during the exercise (manually logged by the user)
    manually_logged_total_steps                     - total steps taken during the exercise (manually logged by the user)
    manually_logged_total_distance_mm               - total distance in millimeters covered during the exercise (manually logged by the user)
    manually_logged_pool_length                     - the pool length in the unit specified by ManuallyLoggedPoolLengthUnit (manually logged by the user)
    manually_logged_pool_length_unit                - the pool length unit

    exercise_events                                 - data about the events that happen throughout the exercise such as start, stop, pause, split
                                                    - for SPLIT, AUTO_SPLIT and INTERVAL events, all the metrics are relative to the previous event
                                                    - for PAUSE, AUTO_PAUSE and STOP events, all the metrics are relative to the start of the exercise
                                                    it is listed as blocks of the following -
                                                    - exercise_event_id: the unique identifier of the event
                                                    - timestamp: the time when the event occurred at UTC
                                                    - type: the type of the event (START, STOP, PAUSE, RESUME etc.)
                                                    - auto_cue_type: the type of the auto cue (MANUAL, DISTANCE, TIME, CALORIES etc.)
                                                    - elapsed_time_millis: the elapsed time in milliseconds
                                                    - traveled_distance_mm: the distance traveled in millimeters
                                                    - calories_burned: the calories burned
                                                    - steps: the steps taken
                                                    - average_heart_rate: average heart rate
                                                    - elevation_gain_mm: elevation gain in millimeters
                                                    - swim_lengths: number of lengths swam
                                                    - average_speed_mm_per_sec: average speed in millimeters per second
                                                    - interval_type: the type of the interval (REST or MOVE)

    activity_type_probabilities                     - a list of activities that the user might have performed during the exercise, with the probability of each activity
    autodetected_confirmed                          - whether the user confirmed the autodetected exercise
    autodetected_start_timestamp                    - the start time of the autodetected exercise at UTC
    autodetected_end_timestamp                      - the end time of the autodetected exercise at UTC
    autodetected_utc_offset                         - the timezone offset relative to UTC for the autodetected exercise
    autodetected_activity_name                      - the name of the autodetected activity
    autodetected_sensor_based_activity_name         - the name of the sensor based autodetected activity
    deletion_reason                                 - the reason why the exercise was deleted
    activity_label                                  - the label of the activity
    suggested_start_timestamp                       - the suggested start time of the exercise at UTC
    suggested_end_timestamp                         - the suggested end time of the exercise at UTC
    reconciliation_status                           - the status of the reconciliation
