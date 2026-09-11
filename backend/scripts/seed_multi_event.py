import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loguru import logger
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.event import Event
from app.models.site import Site
from app.models.camera import Camera
from app.models.user import User
from app.models.user_access import UserEventAccess, UserSiteAccess


async def run():
    logger.info("Starting multi-event and multi-site database initialization...")
    async with AsyncSessionLocal() as session:
        # 1. Update or create KHB-2026 event
        stmt = select(Event).where(Event.code == "KHB-2026")
        res = await session.execute(stmt)
        event = res.scalars().first()

        if event:
            logger.info("Found KHB-2026 event. Updating location fields...")
            event.location = "Khairatabad Circle, Hyderabad"
            event.city = "Hyderabad"
            event.state = "Telangana"
            event.country = "India"
            event.latitude = 17.4175
            event.longitude = 78.4635
            event.is_active = True
            event.status = "ACTIVE"
        else:
            logger.info("Creating KHB-2026 event...")
            event = Event(
                code="KHB-2026",
                name="Khairatabad Ganesh Festival 2026",
                description="Annual 11-day mega festival with estimated 50 lakh pilgrims.",
                year=2026,
                start_date=datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc),
                end_date=datetime(2026, 9, 17, 23, 59, tzinfo=timezone.utc),
                status="ACTIVE",
                is_active=True,
                timezone="Asia/Kolkata",
                location="Khairatabad Circle, Hyderabad",
                city="Hyderabad",
                state="Telangana",
                country="India",
                latitude=17.4175,
                longitude=78.4635,
            )
            session.add(event)
            await session.flush()

        # 2. Seed default sites for KHB-2026
        sites_data = [
            ("SITE-ENTRY", "North & West Entrance Complex", "Entry plaza and security screening gates", "North Gate Corridor", 17.4190, 78.4627),
            ("SITE-DARSHAN", "Main Idol & Darshan Courtyard", "Primary festival idol darshan arena", "Central Sanctum", 17.4175, 78.4635),
            ("SITE-QUEUE", "South Queue Complex", "Multi-tiered zigzag pilgrim queue lines", "South Holding Grounds", 17.4155, 78.4660),
            ("SITE-PRASADAM", "Prasadam & Exit Plaza", "Laddu and prasadam counters with East exit", "East Plaza", 17.4140, 78.4680),
            ("SITE-COMMAND", "Integrated Command Post", "Police, medical, and emergency control operations", "Administrative Block", 17.4165, 78.4715),
        ]

        site_objects = {}
        for scode, sname, sdesc, sloc, lat, lng in sites_data:
            s_stmt = select(Site).where(Site.event_id == event.id, Site.site_code == scode)
            s_res = await session.execute(s_stmt)
            existing_site = s_res.scalars().first()
            if not existing_site:
                new_site = Site(
                    event_id=event.id,
                    site_code=scode,
                    site_name=sname,
                    description=sdesc,
                    location=sloc,
                    latitude=lat,
                    longitude=lng,
                    is_active=True,
                    status="ACTIVE",
                )
                session.add(new_site)
                site_objects[scode] = new_site
                logger.info(f"Created site: {scode} - {sname}")
            else:
                site_objects[scode] = existing_site

        await session.flush()

        # 3. Associate existing cameras with KHB-2026 and SITE-DARSHAN
        cams_stmt = select(Camera)
        cams_res = await session.execute(cams_stmt)
        cams = cams_res.scalars().all()
        darshan_site = site_objects.get("SITE-DARSHAN")
        for cam in cams:
            if not cam.event_id:
                cam.event_id = event.id
            if not cam.site_id and darshan_site:
                cam.site_id = darshan_site.id
            logger.info(f"Scoped camera {cam.camera_code} to event {event.code} and site SITE-DARSHAN")

        # 4. Assign users to KHB-2026 event
        users_stmt = select(User)
        users_res = await session.execute(users_stmt)
        users = users_res.scalars().all()

        role_mapping = {
            "admin": "SUPER_ADMIN",
            "commander": "COMMANDER",
            "operator": "OPERATOR",
            "frs_reviewer": "FRS_OPERATOR",
        }

        for u in users:
            access_stmt = select(UserEventAccess).where(
                UserEventAccess.user_id == u.id,
                UserEventAccess.event_id == event.id,
            )
            access_res = await session.execute(access_stmt)
            existing_acc = access_res.scalars().first()
            if not existing_acc:
                acc_role = role_mapping.get(u.username, "VIEWER")
                new_acc = UserEventAccess(
                    user_id=u.id,
                    event_id=event.id,
                    access_role=acc_role,
                    is_active=True,
                    granted_by="SYSTEM_INIT",
                )
                session.add(new_acc)
                logger.info(f"Assigned user {u.username} to {event.code} with role {acc_role}")

        # 5. Create a sample secondary event for isolation verification: "SEC-2026"
        sec_stmt = select(Event).where(Event.code == "SEC-2026")
        sec_event = (await session.execute(sec_stmt)).scalars().first()
        if not sec_event:
            sec_event = Event(
                code="SEC-2026",
                name="Secunderabad Ganesh Festival 2026",
                description="Secondary city operational zone for Secunderabad Ganesh procession.",
                year=2026,
                start_date=datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc),
                end_date=datetime(2026, 9, 18, 23, 59, tzinfo=timezone.utc),
                status="SCHEDULED",
                is_active=True,
                timezone="Asia/Kolkata",
                location="Secunderabad Clock Tower",
                city="Secunderabad",
                state="Telangana",
                country="India",
                latitude=17.4399,
                longitude=78.4983,
            )
            session.add(sec_event)
            await session.flush()
            logger.info("Created secondary event: SEC-2026")

            # Create site for SEC-2026
            sec_site = Site(
                event_id=sec_event.id,
                site_code="SITE-SEC-MAIN",
                site_name="Secunderabad Clock Tower Junction",
                description="Main staging area for Secunderabad immersion procession",
                location="Clock Tower Circle",
                latitude=17.4399,
                longitude=78.4983,
                is_active=True,
                status="ACTIVE",
            )
            session.add(sec_site)
            logger.info("Created site SITE-SEC-MAIN for SEC-2026")

        await session.commit()
        logger.info("Multi-event & multi-site seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(run())