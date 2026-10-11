import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.event import Event
from app.models.location import Location, LocationVerification
from app.models.site import Site
from app.models.camera import Camera
from app.models.alert import Alert
from app.models.user import User
from app.schemas.event import EventCreate, EventRead
from app.schemas.location import (
    LocationCreate,
    LocationEventCreate,
    LocationRead,
    LocationUpdate,
    VerifyAccessCodeResponse,
)
from app.security.password import get_password_hash, verify_password
from app.services.email_service import email_service
from app.services.event_service import EventService, _normalize_dt

# In-process TTL cache for location list (avoids 13s round-trip to Supabase Sydney on every page load)
_LOCATIONS_CACHE: list = []
_LOCATIONS_CACHE_EXPIRES: float = 0.0


class LocationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_verification_code(
        self,
        email: str,
        location_name: str,
        location_code: Optional[str] = None,
        purpose: str = "CREATE_LOCATION",
    ) -> dict:
        """
        Generates and dispatches a secure 6-digit OTP verification code with location context.
        Enforces 10-minute expiry and rate-limiting.
        """
        email_clean = email.strip().lower()

        # 1. Validation checks per purpose
        if purpose == "CREATE_LOCATION":
            if location_code:
                code_clean = location_code.strip().upper()
                existing = (
                    await self.db.execute(select(Location).where(Location.code == code_clean))
                ).scalars().first()
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Location Code '{code_clean}' is already registered to '{existing.name}'."
                    )
        elif purpose == "RESET_ACCESS_CODE":
            # Ensure email exists for a location
            stmt = select(Location).where(Location.email == email_clean)
            if location_code:
                stmt = stmt.where(Location.code == location_code.strip().upper())
            loc = (await self.db.execute(stmt)).scalars().first()
            if not loc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No location found matching the provided registered email."
                )

        # 2. Invalidate previous active OTPs for this email and purpose
        await self.db.execute(
            update(LocationVerification)
            .where(
                LocationVerification.email == email_clean,
                LocationVerification.purpose == purpose,
                LocationVerification.is_used == False,
            )
            .values(is_used=True)
        )

        # 3. Generate cryptographically secure 6-digit code
        otp_code = str(secrets.randbelow(900000) + 100000)
        code_hash = get_password_hash(otp_code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        verification = LocationVerification(
            email=email_clean,
            location_code=location_code.strip().upper() if location_code else None,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=expires_at,
            is_used=False,
            attempts=0,
        )
        self.db.add(verification)
        await self.db.commit()

        # 4. Dispatch email with location context
        await email_service.send_verification_email(
            to_email=email_clean,
            code=otp_code,
            location_name=location_name,
            purpose=purpose,
        )

        return {"message": "Verification code successfully sent to registered email."}

    async def verify_code(
        self,
        email: str,
        code: str,
        purpose: str,
        consume: bool = True,
    ) -> bool:
        """
        Verifies single-use OTP. Enforces max 5 failed attempts and 10-minute expiry.
        """
        email_clean = email.strip().lower()
        now_utc = datetime.now(timezone.utc)

        stmt = (
            select(LocationVerification)
            .where(
                LocationVerification.email == email_clean,
                LocationVerification.purpose == purpose,
                LocationVerification.is_used == False,
                LocationVerification.expires_at > now_utc,
            )
            .order_by(LocationVerification.created_at.desc())
        )
        res = await self.db.execute(stmt)
        record = res.scalars().first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code is invalid or has expired. Please request a new code.",
            )

        if record.attempts >= 5:
            record.is_used = True
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many incorrect attempts. This verification code has been revoked. Please request a new code.",
            )

        if not verify_password(code.strip(), record.code_hash):
            record.attempts += 1
            await self.db.commit()
            remaining = 5 - record.attempts
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incorrect verification code. {remaining} attempt(s) remaining.",
            )

        if consume:
            record.is_used = True
            await self.db.commit()

        return True

    async def create_location(self, data: LocationCreate, created_by: str) -> LocationRead:
        """
        Creates location after validating single-use email verification code.
        Bcrypt hashes access code so plaintext is never stored.
        """
        code_clean = data.code.strip().upper()
        email_clean = data.email.strip().lower()

        # Check code uniqueness
        existing = (
            await self.db.execute(select(Location).where(Location.code == code_clean))
        ).scalars().first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Location Code '{code_clean}' already exists."
            )

        # Verify OTP
        await self.verify_code(email_clean, data.verification_code, "CREATE_LOCATION", consume=True)

        # Hash access code
        access_code_hash = get_password_hash(data.access_code.strip())

        new_loc = Location(
            code=code_clean,
            name=data.name.strip(),
            city=data.city.strip(),
            state=data.state.strip(),
            email=email_clean,
            access_code_hash=access_code_hash,
            status="ACTIVE",
            is_active=True,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(new_loc)
        await self.db.commit()
        await self.db.refresh(new_loc)

        return LocationRead(
            id=new_loc.id,
            code=new_loc.code,
            name=new_loc.name,
            city=new_loc.city,
            state=new_loc.state,
            email=new_loc.email,
            status=new_loc.status,
            is_active=new_loc.is_active,
            created_at=new_loc.created_at,
            updated_at=new_loc.updated_at,
            created_by=new_loc.created_by,
            updated_by=new_loc.updated_by,
            festival_count=0,
        )

    async def list_locations(self) -> List[LocationRead]:
        """
        Lists all active locations with dynamic festival/event counts.
        Results are cached 30 seconds in-process to avoid repeated round-trips
        to Supabase Sydney (each DB query = ~6.5 s from Hyderabad).
        """
        global _LOCATIONS_CACHE, _LOCATIONS_CACHE_EXPIRES
        now = time.monotonic()
        if _LOCATIONS_CACHE and now < _LOCATIONS_CACHE_EXPIRES:
            return _LOCATIONS_CACHE

        stmt = select(Location).order_by(Location.is_active.desc(), Location.name.asc())
        locations = (await self.db.execute(stmt)).scalars().all()

        if not locations:
            _LOCATIONS_CACHE = []
            _LOCATIONS_CACHE_EXPIRES = now + 30.0
            return []

        loc_ids = [loc.id for loc in locations]
        count_stmt = (
            select(Event.location_id, func.count(Event.id))
            .where(Event.location_id.in_(loc_ids))
            .group_by(Event.location_id)
        )
        counts = dict((await self.db.execute(count_stmt)).all())

        results = []
        for loc in locations:
            results.append(
                LocationRead(
                    id=loc.id,
                    code=loc.code,
                    name=loc.name,
                    city=loc.city,
                    state=loc.state,
                    email=loc.email,
                    status=loc.status,
                    is_active=loc.is_active,
                    created_at=loc.created_at,
                    updated_at=loc.updated_at,
                    created_by=loc.created_by,
                    updated_by=loc.updated_by,
                    festival_count=counts.get(loc.id, 0),
                )
            )
        _LOCATIONS_CACHE = results
        _LOCATIONS_CACHE_EXPIRES = now + 30.0
        return results


    async def get_location_by_id(self, location_id: uuid.UUID) -> LocationRead:
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        count = (
            await self.db.execute(select(func.count(Event.id)).where(Event.location_id == location_id))
        ).scalar() or 0

        return LocationRead(
            id=loc.id,
            code=loc.code,
            name=loc.name,
            city=loc.city,
            state=loc.state,
            email=loc.email,
            status=loc.status,
            is_active=loc.is_active,
            created_at=loc.created_at,
            updated_at=loc.updated_at,
            created_by=loc.created_by,
            updated_by=loc.updated_by,
            festival_count=count,
        )

    async def update_location(self, location_id: uuid.UUID, data: LocationUpdate, updated_by: str) -> LocationRead:
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        update_dict = data.model_dump(exclude_unset=True)
        for k, v in update_dict.items():
            setattr(loc, k, v)
        loc.updated_by = updated_by
        await self.db.commit()
        await self.db.refresh(loc)

        count = (
            await self.db.execute(select(func.count(Event.id)).where(Event.location_id == location_id))
        ).scalar() or 0

        return LocationRead(
            id=loc.id,
            code=loc.code,
            name=loc.name,
            city=loc.city,
            state=loc.state,
            email=loc.email,
            status=loc.status,
            is_active=loc.is_active,
            created_at=loc.created_at,
            updated_at=loc.updated_at,
            created_by=loc.created_by,
            updated_by=loc.updated_by,
            festival_count=count,
        )

    async def verify_access_code(self, location_id: uuid.UUID, access_code: str) -> VerifyAccessCodeResponse:
        """
        Verifies access code against stored bcrypt hash.
        Never reveals or retrieves stored code.
        """
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        if not loc.is_active or loc.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Location is currently inactive")

        if not verify_password(access_code.strip(), loc.access_code_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect access code for this location. Access denied."
            )

        return VerifyAccessCodeResponse(
            verified=True,
            location_id=loc.id,
            location_name=loc.name,
            location_code=loc.code,
            message="Location access code verified successfully."
        )

    async def forgot_access_code(self, location_id: uuid.UUID, email: str) -> dict:
        """
        Sends recovery OTP to registered email.
        """
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        if loc.email.lower() != email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provided email does not match the registered location email."
            )

        return await self.send_verification_code(
            email=loc.email,
            location_name=loc.name,
            location_code=loc.code,
            purpose="RESET_ACCESS_CODE",
        )

    async def reset_access_code(
        self,
        location_id: uuid.UUID,
        email: str,
        verification_code: str,
        new_access_code: str,
        updated_by: str = "SYSTEM",
    ) -> dict:
        """
        Verifies recovery OTP, hashes new access code, and invalidates old code.
        Never reveals old code.
        """
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        if loc.email.lower() != email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provided email does not match the registered location email."
            )

        # Verify OTP
        await self.verify_code(email, verification_code, "RESET_ACCESS_CODE", consume=True)

        # Hash new access code
        loc.access_code_hash = get_password_hash(new_access_code.strip())
        loc.updated_by = updated_by
        await self.db.commit()

        logger.info(f"[LocationService] Access code reset successfully for location '{loc.name}' ({loc.code})")
        return {"message": "Location access code has been reset successfully."}

    async def list_location_events(self, location_id: uuid.UUID, user: User) -> List[EventRead]:
        """
        Lists all festivals / events belonging to this location.
        Reuses existing Event model and timing lifecycle evaluation.
        """
        # Ensure location exists
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        stmt = (
            select(Event)
            .where(Event.location_id == location_id)
            .order_by(Event.is_active.desc(), Event.start_date.desc())
        )
        events = (await self.db.execute(stmt)).scalars().all()

        if not events:
            return []

        # Run timing lifecycle evaluation
        event_svc = EventService(self.db)
        now_utc = datetime.now(timezone.utc)
        changed = False
        for e in events:
            if event_svc._evaluate_timing_lifecycle(e, now_utc):
                changed = True
        if changed:
            await self.db.commit()

        event_ids = [e.id for e in events]

        # Aggregate site counts
        site_counts = dict(
            (
                await self.db.execute(
                    select(Site.event_id, func.count(Site.id))
                    .where(Site.event_id.in_(event_ids))
                    .group_by(Site.event_id)
                )
            ).all()
        )

        # Aggregate camera counts
        cam_counts = dict(
            (
                await self.db.execute(
                    select(Camera.event_id, func.count(Camera.id))
                    .where(Camera.event_id.in_(event_ids))
                    .group_by(Camera.event_id)
                )
            ).all()
        )

        # Aggregate active alert counts
        alert_counts = dict(
            (
                await self.db.execute(
                    select(Alert.event_id, func.count(Alert.id))
                    .where(Alert.event_id.in_(event_ids), Alert.status == "ACTIVE")
                    .group_by(Alert.event_id)
                )
            ).all()
        )

        results = []
        for e in events:
            results.append(
                EventRead(
                    id=e.id,
                    code=e.code,
                    name=e.name,
                    description=e.description,
                    year=e.year,
                    start_date=e.start_date,
                    end_date=e.end_date,
                    status=e.status,
                    is_active=e.is_active,
                    timezone=e.timezone,
                    location=e.location,
                    city=e.city,
                    state=e.state,
                    country=e.country,
                    latitude=e.latitude,
                    longitude=e.longitude,
                    created_at=e.created_at,
                    updated_at=e.updated_at,
                    created_by=e.created_by,
                    updated_by=e.updated_by,
                    site_count=site_counts.get(e.id, 0),
                    camera_count=cam_counts.get(e.id, 0),
                    active_alert_count=alert_counts.get(e.id, 0),
                    user_access_role="SUPER_ADMIN" if user.is_super_admin else "VIEWER",
                )
            )
        return results

    async def create_location_event(
        self,
        location_id: uuid.UUID,
        data: LocationEventCreate,
        created_by: str,
    ) -> EventRead:
        """
        Adds a new festival/event directly under the selected Location.
        Reuses the existing Event model and EventService logic without duplicate tables.
        """
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        # Check duplicate event code
        code_clean = data.code.strip().upper()
        existing = (
            await self.db.execute(select(Event).where(Event.code == code_clean))
        ).scalars().first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Event Code '{code_clean}' already exists."
            )

        now_utc = datetime.now(timezone.utc)
        s_utc = _normalize_dt(data.start_date)
        e_utc = _normalize_dt(data.end_date)

        status_val = data.status
        is_active_val = data.is_active
        if status_val == "SCHEDULED" and s_utc and e_utc:
            if s_utc <= now_utc <= e_utc:
                status_val = "ACTIVE"
                is_active_val = True
            elif now_utc > e_utc:
                status_val = "COMPLETED"
                is_active_val = False

        new_event = Event(
            code=code_clean,
            name=data.name.strip(),
            description=data.description,
            year=data.year,
            start_date=data.start_date,
            end_date=data.end_date,
            status=status_val,
            is_active=is_active_val,
            timezone=data.timezone,
            location=data.location or loc.name,
            city=data.city or loc.city,
            state=data.state or loc.state,
            country=data.country or "India",
            location_id=loc.id,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(new_event)
        await self.db.commit()
        await self.db.refresh(new_event)

        logger.info(f"[LocationService] Added new festival '{new_event.name}' ({new_event.code}) to location '{loc.name}'")

        return EventRead(
            id=new_event.id,
            code=new_event.code,
            name=new_event.name,
            description=new_event.description,
            year=new_event.year,
            start_date=new_event.start_date,
            end_date=new_event.end_date,
            status=new_event.status,
            is_active=new_event.is_active,
            timezone=new_event.timezone,
            location=new_event.location,
            city=new_event.city,
            state=new_event.state,
            country=new_event.country,
            created_at=new_event.created_at,
            updated_at=new_event.updated_at,
            created_by=new_event.created_by,
            updated_by=new_event.updated_by,
            site_count=0,
            camera_count=0,
            active_alert_count=0,
            user_access_role="SUPER_ADMIN",
        )

    async def link_existing_event(
        self,
        location_id: uuid.UUID,
        event_id: uuid.UUID,
        updated_by: str,
    ) -> dict:
        """
        Deliberate administrative association step (Safeguard #1).
        Associates an existing event with a location without auto-linking.
        """
        loc = (
            await self.db.execute(select(Location).where(Location.id == location_id))
        ).scalars().first()
        if not loc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

        evt = (
            await self.db.execute(select(Event).where(Event.id == event_id))
        ).scalars().first()
        if not evt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

        evt.location_id = loc.id
        evt.updated_by = updated_by
        await self.db.commit()

        logger.info(f"[LocationService] Deliberately linked event '{evt.name}' to location '{loc.name}' by {updated_by}")
        return {
            "message": f"Event '{evt.name}' successfully associated with Location '{loc.name}'.",
            "event_id": str(evt.id),
            "location_id": str(loc.id),
        }
