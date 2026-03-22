Premium Subscriptions

The below section is dedicated to the exported data of user's premium subscriptions.

Files Included:
----------
UserPremiumSubscriptions.csv

The data for premium subscriptions

    subscription_id                          - id of the subscription
    provider                                 - provider of the subscription, e.g. 'PROVIDER_APPLE', 'PROVIDER_GOOGLE'
    sku                                      - sku of the subscription
    start_time                               - start time of the subscription, timestamp
    expiration_time                          - expiration time of the subscription, timestamp
    access_granted_until_time                - access granted until time of the subscription, timestamp
    cancellation_time                        - cancellation time of the subscription, timestamp
    trial_period_end_time                    - trial period end time of the subscription, timestamp
    state                                    - state of the subscription, e.g. 'SUBSCRIPTION_STATE_ACTIVE', 'SUBSCRIPTION_STATE_EXPIRED'
    updated_time                             - last update time of the subscription, timestamp

    apple_original_transaction_id            - apple original transaction id
    apple_validate_at_time                   - apple validate at time, timestamp
    apple_fatal_renewal_error                - apple fatal renewal error, 'true' or 'false'
    apple_last_transaction_time              - apple last transaction time, timestamp

    google_store_subscription_id             - google store subscription id
    google_store_line_item_id                - google store line item id

    google_validate_at_time                  - google validate at time, timestamp
    google_last_transaction_id               - google last transaction id