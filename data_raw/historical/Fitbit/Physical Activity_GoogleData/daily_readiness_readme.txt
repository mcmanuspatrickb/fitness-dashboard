Time Series Data Export

The Time Series export provides a detailed timeline of your tracked activity.

Files Included:
----------

daily_readiness.csv                   - Contains all data for this type.

Daily Readiness represents how ready the user is for activity, based on sleep, heart rate variability and resting heart rate.
Each entry has the following values:

    timestamp                         - Date at which the entry was logged in UTC.
    score                             - Overall score based on the other metrics. Values can range from 1 to 100.
    type                              - Overall readiness rating type. Values can be LOW, MEDIUM or HIGH.
    readiness level                   - Readiness rating level. Values can be VERY LOW, LOW, BALANCED, HIGH, PEAK.
    sleep readiness                   - Readiness rating based on sleep. Values can be VERY LOW, LOW, MEDIUM, HIGH, VERY HIGH, IGNORED or NOT AVAILABLE.
    heart rate variability readiness  - Readiness rating based on heart rate variability. Values can be VERY LOW, LOW, MEDIUM, HIGH, VERY HIGH.
    resting heart rate readiness      - Readiness rating based on resting heart rate. Values can be VERY LOW, LOW, MEDIUM, HIGH, VERY HIGH or IGNORED.
    data source                       - The origin or source of this data.
