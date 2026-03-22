Time Series Data Export

The Time Series export provides a detailed timeline of your tracked activity.

Files Included:
----------

daily_sleep_temperature_derivations.csv - Contains all data for this type.

Each entry has the following values:

    timestamp                           - Date and time at which the entry was logged.
    nightly temperature celsius         - The mean of skin temperature samples taken from the user's sleep.
    baseline temperature celsius        - The median of the user's nightly skin temperature over the past 30 days.
    relative nightly stddev 30d celsius - The standard deviation of the user's relative nightly skin temperature(temperature - baseline) over the past 30 days.
    data source                         - The origin or source of this data.
