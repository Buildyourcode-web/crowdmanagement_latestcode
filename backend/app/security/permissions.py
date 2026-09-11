# Permission string definitions for Role-Based Access Control

class Permissions:
    # Camera permissions
    CAMERA_READ = "camera:read"
    CAMERA_MANAGE = "camera:manage"

    # Zone & Gate permissions
    ZONE_READ = "zone:read"
    ZONE_MANAGE = "zone:manage"

    # Crowd intelligence permissions
    CROWD_READ = "crowd:read"
    CROWD_MANAGE = "crowd:manage"

    # Queue intelligence permissions
    QUEUE_READ = "queue:read"
    QUEUE_MANAGE = "queue:manage"

    # FRS (Facial Recognition) permissions - Strictly isolated
    FRS_READ = "frs:read"
    FRS_REVIEW = "frs:review"
    FRS_MANAGE = "frs:manage"

    # Missing person permissions
    MISSING_PERSON_READ = "missing_person:read"
    MISSING_PERSON_MANAGE = "missing_person:manage"

    # Alerts & Incidents permissions
    ALERT_READ = "alert:read"
    ALERT_MANAGE = "alert:manage"
    INCIDENT_READ = "incident:read"
    INCIDENT_MANAGE = "incident:manage"

    # Operations & Dispatch permissions
    OPERATIONS_READ = "operations:read"
    OPERATIONS_MANAGE = "operations:manage"

    # Analytics & Reports
    ANALYTICS_READ = "analytics:read"
    REPORTS_READ = "reports:read"
    REPORTS_EXPORT = "reports:export"

    # System & Audit
    SYSTEM_READ = "system:read"
    SYSTEM_MANAGE = "system:manage"
    AUDIT_READ = "audit:read"

    # AI Orchestration & Runtime permissions
    AI_READ = "ai:read"
    AI_MANAGE = "ai:manage"

    # ── Settings permissions ──────────────────────────────────────────────────
    SETTINGS_READ = "settings:read"
    SETTINGS_UPDATE = "settings:update"

    EVENT_SETTINGS_READ = "event_settings:read"
    EVENT_SETTINGS_UPDATE = "event_settings:update"

    ZONE_SETTINGS_READ = "zone_settings:read"
    ZONE_SETTINGS_UPDATE = "zone_settings:update"

    CAMERA_SETTINGS_READ = "camera_settings:read"
    CAMERA_SETTINGS_UPDATE = "camera_settings:update"

    ALERT_SETTINGS_READ = "alert_settings:read"
    ALERT_SETTINGS_UPDATE = "alert_settings:update"

    ROLE_READ = "role:read"
    ROLE_UPDATE = "role:update"
    ROLE_CREATE = "role:create"

    NOTIFICATION_SETTINGS_READ = "notification_settings:read"
    NOTIFICATION_SETTINGS_UPDATE = "notification_settings:update"

    AI_SETTINGS_READ = "ai_settings:read"
    AI_SETTINGS_UPDATE = "ai_settings:update"

    FRS_SETTINGS_READ = "frs_settings:read"
    FRS_SETTINGS_UPDATE = "frs_settings:update"

    SYSTEM_SETTINGS_READ = "system_settings:read"
    SYSTEM_SETTINGS_UPDATE = "system_settings:update"

    # ── Event & Site management permissions ──────────────────────────────────
    EVENT_CREATE = "event:create"
    EVENT_READ = "event:read"
    EVENT_UPDATE = "event:update"
    EVENT_ARCHIVE = "event:archive"
    EVENT_ACCESS_MANAGE = "event:access_manage"  # Grant/revoke user event access

    SITE_CREATE = "site:create"
    SITE_READ = "site:read"
    SITE_UPDATE = "site:update"
    SITE_DELETE = "site:delete"

    # ── Predictions ───────────────────────────────────────────────────────────
    PREDICTION_READ = "prediction:read"



# Standard role mappings
DEFAULT_ROLE_PERMISSIONS = {
    "SUPER_ADMIN": [
        Permissions.CAMERA_READ, Permissions.CAMERA_MANAGE,
        Permissions.ZONE_READ, Permissions.ZONE_MANAGE,
        Permissions.CROWD_READ, Permissions.CROWD_MANAGE,
        Permissions.QUEUE_READ, Permissions.QUEUE_MANAGE,
        Permissions.FRS_READ, Permissions.FRS_REVIEW, Permissions.FRS_MANAGE,
        Permissions.MISSING_PERSON_READ, Permissions.MISSING_PERSON_MANAGE,
        Permissions.ALERT_READ, Permissions.ALERT_MANAGE,
        Permissions.INCIDENT_READ, Permissions.INCIDENT_MANAGE,
        Permissions.OPERATIONS_READ, Permissions.OPERATIONS_MANAGE,
        Permissions.ANALYTICS_READ, Permissions.REPORTS_READ, Permissions.REPORTS_EXPORT,
        Permissions.SYSTEM_READ, Permissions.SYSTEM_MANAGE, Permissions.AUDIT_READ,
        Permissions.AI_READ, Permissions.AI_MANAGE,
        Permissions.PREDICTION_READ,
        # Settings
        Permissions.SETTINGS_READ, Permissions.SETTINGS_UPDATE,
        Permissions.EVENT_SETTINGS_READ, Permissions.EVENT_SETTINGS_UPDATE,
        Permissions.ZONE_SETTINGS_READ, Permissions.ZONE_SETTINGS_UPDATE,
        Permissions.CAMERA_SETTINGS_READ, Permissions.CAMERA_SETTINGS_UPDATE,
        Permissions.ALERT_SETTINGS_READ, Permissions.ALERT_SETTINGS_UPDATE,
        Permissions.ROLE_READ, Permissions.ROLE_UPDATE, Permissions.ROLE_CREATE,
        Permissions.NOTIFICATION_SETTINGS_READ, Permissions.NOTIFICATION_SETTINGS_UPDATE,
        Permissions.AI_SETTINGS_READ, Permissions.AI_SETTINGS_UPDATE,
        Permissions.FRS_SETTINGS_READ, Permissions.FRS_SETTINGS_UPDATE,
        Permissions.SYSTEM_SETTINGS_READ, Permissions.SYSTEM_SETTINGS_UPDATE,
        # Event & Site management
        Permissions.EVENT_CREATE, Permissions.EVENT_READ, Permissions.EVENT_UPDATE, Permissions.EVENT_ARCHIVE,
        Permissions.EVENT_ACCESS_MANAGE,
        Permissions.SITE_CREATE, Permissions.SITE_READ, Permissions.SITE_UPDATE, Permissions.SITE_DELETE,
    ],
    "COMMANDER": [
        Permissions.CAMERA_READ, Permissions.CAMERA_MANAGE,
        Permissions.ZONE_READ,
        Permissions.CROWD_READ,
        Permissions.FRS_READ, Permissions.FRS_REVIEW,
        Permissions.MISSING_PERSON_READ, Permissions.MISSING_PERSON_MANAGE,
        Permissions.ALERT_READ, Permissions.ALERT_MANAGE,
        Permissions.INCIDENT_READ, Permissions.INCIDENT_MANAGE,
        Permissions.OPERATIONS_READ, Permissions.OPERATIONS_MANAGE,
        Permissions.ANALYTICS_READ, Permissions.REPORTS_READ, Permissions.REPORTS_EXPORT,
        Permissions.SYSTEM_READ, Permissions.AUDIT_READ,
        Permissions.AI_READ,
        Permissions.PREDICTION_READ,
        # Settings (read + limited update)
        Permissions.SETTINGS_READ,
        Permissions.EVENT_SETTINGS_READ, Permissions.EVENT_SETTINGS_UPDATE,
        Permissions.ZONE_SETTINGS_READ, Permissions.ZONE_SETTINGS_UPDATE,
        Permissions.CAMERA_SETTINGS_READ, Permissions.CAMERA_SETTINGS_UPDATE,
        Permissions.ALERT_SETTINGS_READ, Permissions.ALERT_SETTINGS_UPDATE,
        Permissions.ROLE_READ,
        Permissions.NOTIFICATION_SETTINGS_READ,
        Permissions.AI_SETTINGS_READ,
        Permissions.FRS_SETTINGS_READ,
        Permissions.SYSTEM_SETTINGS_READ,
        # Event & Site (can read + update, not create/archive events)
        Permissions.EVENT_READ, Permissions.EVENT_UPDATE, Permissions.EVENT_ACCESS_MANAGE,
        Permissions.SITE_CREATE, Permissions.SITE_READ, Permissions.SITE_UPDATE, Permissions.SITE_DELETE,
    ],
    "CONTROL_ROOM": [
        Permissions.CAMERA_READ,
        Permissions.ZONE_READ,
        Permissions.CROWD_READ,
        Permissions.ALERT_READ, Permissions.ALERT_MANAGE,
        Permissions.INCIDENT_READ, Permissions.INCIDENT_MANAGE,
        Permissions.OPERATIONS_READ,
        Permissions.ANALYTICS_READ, Permissions.REPORTS_READ,
        Permissions.SYSTEM_READ,
        Permissions.PREDICTION_READ,
        # Settings (read-only)
        Permissions.SETTINGS_READ,
        Permissions.EVENT_SETTINGS_READ,
        Permissions.ZONE_SETTINGS_READ,
        Permissions.CAMERA_SETTINGS_READ,
        Permissions.ALERT_SETTINGS_READ,
        Permissions.NOTIFICATION_SETTINGS_READ,
        Permissions.SYSTEM_SETTINGS_READ,
        # Event & Site (read only)
        Permissions.EVENT_READ,
        Permissions.SITE_READ,
    ],
    "FRS_OPERATOR": [
        Permissions.FRS_READ, Permissions.FRS_REVIEW,
        Permissions.MISSING_PERSON_READ,
        Permissions.ALERT_READ,
        Permissions.SYSTEM_READ,
        Permissions.FRS_SETTINGS_READ,
        Permissions.SETTINGS_READ,
        Permissions.EVENT_READ,
        Permissions.SITE_READ,
    ],
    "POLICE_OPERATOR": [
        Permissions.CAMERA_READ,
        Permissions.ZONE_READ,
        Permissions.CROWD_READ,
        Permissions.ALERT_READ, Permissions.ALERT_MANAGE,
        Permissions.INCIDENT_READ, Permissions.INCIDENT_MANAGE,
        Permissions.OPERATIONS_READ, Permissions.OPERATIONS_MANAGE,
        Permissions.SETTINGS_READ,
        Permissions.EVENT_READ,
        Permissions.SITE_READ,
    ],
    "MEDICAL_OPERATOR": [
        Permissions.ZONE_READ,
        Permissions.ALERT_READ,
        Permissions.INCIDENT_READ, Permissions.INCIDENT_MANAGE,
        Permissions.OPERATIONS_READ, Permissions.OPERATIONS_MANAGE,
        Permissions.SETTINGS_READ,
        Permissions.EVENT_READ,
        Permissions.SITE_READ,
    ],
    "VIEWER": [
        Permissions.CAMERA_READ,
        Permissions.ZONE_READ,
        Permissions.CROWD_READ,
        Permissions.ALERT_READ,
        Permissions.ANALYTICS_READ,
        Permissions.SETTINGS_READ,
        Permissions.EVENT_READ,
        Permissions.SITE_READ,
    ],
}

