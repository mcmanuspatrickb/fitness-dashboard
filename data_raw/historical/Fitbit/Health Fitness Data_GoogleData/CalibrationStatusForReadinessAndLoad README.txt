Calibration Status for Readiness and Load

The CalibrationStatusForReadinessAndLoad file contains the calibration status for the Readiness and Load features.
When the remaining number of days is 0, the user is considered calibrated.

----------

CalibrationStatusForReadinessAndLoad.csv

  user_id                            - unique id for the user
  feature                            - name of the feature
  remaining_days                     - the remaining number of days required to complete the calibration
  calibration_start_date             - the date when calibration was started, local date
  latest_completion_date             - the date when calibration was completed, local date
  latest_update_date                 - the date when the calibration status was last updated, local date