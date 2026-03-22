Time Series Data Export

The Time Series export provides a detailed timeline of your tracked activity.

Files Included:
----------

cardio_load_observed_interval.csv     - Contains all data for this type.

Cardio load observed interval measures the personalized cardio load interval for a user.
Each entry has the following values:

    timestamp                         - Date at which the entry was logged in UTC.
    min observed load                 - Average of top 3 lowest cardio load values over a period of 4 weeks.
    max observed load                 - average of top 3 highest cardio load values over a period of 4 weeks.
    data source                       - The origin or source of this data.
