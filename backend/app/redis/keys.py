# Redis Channel and Key Constants

class RedisChannels:
    CROWD = "byc:crowd"
    ALERTS = "byc:alerts"
    FRS = "byc:frs"
    CAMERAS = "byc:cameras"
    INCIDENTS = "byc:incidents"
    OPERATIONS = "byc:operations"
    SYSTEM = "byc:system"
    ALL_EVENTS = "byc:events:*"


class RedisKeys:
    CROWD_SUMMARY = "byc:cache:crowd_summary"
    ZONE_METRICS = "byc:cache:zone_metrics"
    CAMERA_HEALTH = "byc:cache:camera_health"
    SYSTEM_HEALTH = "byc:cache:system_health"
