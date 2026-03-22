Irregular Rhythm Notifications

The below section is dedicated to the exported data of the Irregular Rhythm
Notifications (IRN) data domain. The IRN feature analyzes your heart rhythm for
signs of atrial fibrillation (AFib).

Files Included:
----------

IrnUserState.csv

The data for the user's state with respect to the Irregular Rhythm Notifications feature.

    EnrollmentState          - The user's enrollment status in the IRN feature
                               (e.g., ENROLLED).
    LastProcessedTime        - The timestamp of the last time the user's heart
                               rhythm data was processed.
    LastConclusiveWindow     - The timestamp of the end of the last window of
                               data that was considered conclusive (either positive or negative for AFib).
    LastProcessedTimestamps  - A JSON array detailing the last processed
                               timestamp for each data source (e.g., each device).
    LastNotifiedTime         - The timestamp of the last time a notification was
                               sent to the user.


IrnAfibAlertWindows.csv

The data for individual AFib analysis windows. An alert is generated from one or more of these windows.

    DeviceId                 - The identifier of the device that recorded the
                               data.
    DeviceFitbitDeviceType   - The model of the Fitbit device (e.g., ANTARES).
    AlgorithmVersion         - The version of the AFib detection algorithm used.
    ServiceVersion           - The version of the backend service that processed
                               the data.
    StartTime                - The start time of the analysis window.
    Positive                 - A boolean indicating if the window was positive
                               for signs of AFib.
    HeartBeats               - A JSON array of heartbeats recorded during the
                               window, including the timestamp and beats per
                               minute for each.


IrnAfibAlerts.csv

The data for AFib alerts sent to the user.

    DeviceId                 - The identifier of the device that recorded the
                               data.
    DeviceFitbitDeviceType   - The model of the Fitbit device.
    AlgorithmVersion         - The version of the AFib detection algorithm used.
    ServiceVersion           - The version of the backend service that processed
                               the data.
    StartTime                - The start time of the first analysis window in
                               the alert.
    EndTime                  - The end time of the last analysis window in the
                               alert.
    DetectedTime             - The timestamp when the alert was officially
                               generated.
    AlertWindows             - A JSON array of the individual analysis windows
                               that constitute the alert. Each window includes
                               its start and end times, a positive flag, and the
                               associated heartbeats.
    IsRead                   - A boolean indicating if the user has viewed the
                               notification.
