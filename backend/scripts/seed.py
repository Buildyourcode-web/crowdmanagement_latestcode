import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loguru import logger
from sqlalchemy import select
from app.db.base import Base
from app.db.session import AsyncSessionLocal, async_engine
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.crowd import CrowdSnapshot
from app.models.event import Event
from app.models.frs import FRSAuditLog, FRSCandidate, FRSReferenceProfile, FRSReview
from app.models.gate import Gate
from app.models.incident import Incident, IncidentNote
from app.models.missing_person import MissingPersonCase
from app.models.operation import EmergencyRoute, MedicalUnit, PoliceUnit
from app.models.queue import QueueSnapshot
from app.models.role import Permission, Role
from app.models.user import User
from app.models.zone import Zone
from app.security.password import get_password_hash
from app.security.permissions import DEFAULT_ROLE_PERMISSIONS, Permissions


async def seed_data():
    logger.info("Starting seed data population for Supabase...")

    async with AsyncSessionLocal() as session:
        # 1. Seed Permissions & Roles
        existing_roles = (await session.execute(select(Role))).scalars().all()
        if not existing_roles:
            logger.info("Seeding Permissions and Roles...")
            all_perm_codes = set()
            for perms in DEFAULT_ROLE_PERMISSIONS.values():
                all_perm_codes.update(perms)

            perm_objects = {}
            for code in all_perm_codes:
                p = Permission(code=code, name=code.replace(":", " ").title(), description=f"Permission for {code}")
                session.add(p)
                perm_objects[code] = p

            await session.flush()

            role_objects = {}
            for role_code, perms in DEFAULT_ROLE_PERMISSIONS.items():
                r = Role(
                    code=role_code,
                    name=role_code.replace("_", " ").title(),
                    description=f"{role_code} role",
                    permissions=[perm_objects[c] for c in perms if c in perm_objects],
                )
                session.add(r)
                role_objects[role_code] = r

            await session.flush()

            # 2. Seed Users
            logger.info("Seeding default administrative and operator users...")
            users_data = [
                ("admin", "admin@byc.gov.in", "admin123", "Chief Commissioner Reddy", "SUPER_ADMIN"),
                ("commander", "commander@byc.gov.in", "commander123", "Cmd Officer Sharma", "COMMANDER"),
                ("operator", "operator@byc.gov.in", "operator123", "Ctrl Operator Rajesh", "CONTROL_ROOM"),
                ("frs_reviewer", "frs@byc.gov.in", "frs123", "FRS Review Officer Ananya", "FRS_OPERATOR"),
            ]
            for uname, email, pwd, fname, rcode in users_data:
                u = User(
                    username=uname,
                    email=email,
                    password_hash=get_password_hash(pwd),
                    full_name=fname,
                    role_id=role_objects[rcode].id,
                    is_active=True,
                )
                session.add(u)

        # 3. Seed Event
        existing_event = (await session.execute(select(Event))).scalars().first()
        if not existing_event:
            logger.info("Seeding Khairatabad Ganesh Festival 2026 Event...")
            fest_event = Event(
                code="KHB-2026",
                name="Khairatabad Ganesh Festival 2026",
                description="Annual 11-day mega festival with estimated 50 lakh pilgrims.",
                year=2026,
                start_date=datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc),
                end_date=datetime(2026, 9, 17, 23, 59, tzinfo=timezone.utc),
                status="ACTIVE",
            )
            session.add(fest_event)
            await session.flush()

        # 4. Seed Zones
        existing_zones = (await session.execute(select(Zone))).scalars().all()
        if not existing_zones:
            logger.info("Seeding 12 Operational Zones...")
            raw_zones = [
                ("ZONE-A", "Zone A", "North Gate & Approach", 10000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4610, 17.4190], [78.4645, 17.4190], [78.4645, 17.4165], [78.4610, 17.4165]], [78.4627, 17.4177]),
                ("ZONE-B", "Zone B", "Main Idol Darshan Arena", 20000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4645, 17.4190], [78.4680, 17.4190], [78.4680, 17.4165], [78.4645, 17.4165]], [78.4662, 17.4177]),
                ("ZONE-C", "Zone C", "VIP Enclosure & Stage", 6000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4680, 17.4190], [78.4715, 17.4190], [78.4715, 17.4165], [78.4680, 17.4165]], [78.4697, 17.4177]),
                ("ZONE-D", "Zone D", "Prasadam & Laddu Counters", 5000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4610, 17.4165], [78.4645, 17.4165], [78.4645, 17.4140], [78.4610, 17.4140]], [78.4627, 17.4152]),
                ("ZONE-E", "Zone E", "South Queue Complex", 8000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4645, 17.4165], [78.4680, 17.4165], [78.4680, 17.4140], [78.4645, 17.4140]], [78.4662, 17.4152]),
                ("ZONE-F", "Zone F", "Police & Emergency Post", 3000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4680, 17.4165], [78.4715, 17.4165], [78.4715, 17.4140], [78.4680, 17.4140]], [78.4697, 17.4152]),
                ("ZONE-G", "Zone G", "Medical Response Centre", 2000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4610, 17.4140], [78.4645, 17.4140], [78.4645, 17.4115], [78.4610, 17.4115]], [78.4627, 17.4127]),
                ("ZONE-H", "Zone H", "East Exit Plaza", 10000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4645, 17.4140], [78.4680, 17.4140], [78.4680, 17.4115], [78.4645, 17.4115]], [78.4662, 17.4127]),
                ("ZONE-I", "Zone I", "Media & Broadcast Compound", 2500, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4680, 17.4140], [78.4715, 17.4140], [78.4715, 17.4115], [78.4680, 17.4115]], [78.4697, 17.4127]),
                ("ZONE-J", "Zone J", "North-West Parking", 4000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4575, 17.4190], [78.4610, 17.4190], [78.4610, 17.4165], [78.4575, 17.4165]], [78.4592, 17.4177]),
                ("ZONE-K", "Zone K", "South Transit Corridor", 8000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4645, 17.4115], [78.4680, 17.4115], [78.4680, 17.4090], [78.4645, 17.4090]], [78.4662, 17.4102]),
                ("ZONE-L", "Zone L", "Flyover Underpass Buffer", 5000, 0, 0.0, "LOW", "LOW", "#3fb950", [[78.4680, 17.4115], [78.4715, 17.4115], [78.4715, 17.4090], [78.4680, 17.4090]], [78.4697, 17.4102]),
            ]
            for zcode, name, label, cap, cur, dens, dens_lbl, risk, col, coords, center in raw_zones:
                z = Zone(
                    zone_code=zcode,
                    name=name,
                    label=label,
                    description=f"{label} for crowd management",
                    capacity=cap,
                    current_people=cur,
                    density=dens,
                    density_label=dens_lbl,
                    risk_level=risk,
                    color=col,
                    coordinates=coords,
                    center=center,
                )
                session.add(z)
            await session.flush()

        # 5. Seed Gates
        existing_gates = (await session.execute(select(Gate))).scalars().all()
        if not existing_gates:
            logger.info("Seeding 8 Access Gates...")
            raw_gates = [
                ("GATE-01", "Gate 1", "North Entry Gate 1", "ZONE-A", [78.4615, 17.4185], "ENTRY", 145, 200),
                ("GATE-02", "Gate 2", "North Entry Gate 2", "ZONE-A", [78.4635, 17.4185], "ENTRY", 110, 200),
                ("GATE-03", "Gate 3", "VIP North Gate", "ZONE-B", [78.4655, 17.4185], "ENTRY", 90, 150),
                ("GATE-04", "Gate 4", "East VIP Exit", "ZONE-C", [78.4695, 17.4180], "EXIT", 67, 150),
                ("GATE-05", "Gate 5", "Prasadam Fast Gate", "ZONE-D", [78.4625, 17.4150], "BOTH", 34, 100),
                ("GATE-06", "Gate 6", "South Main Queue Gate", "ZONE-E", [78.4660, 17.4155], "ENTRY", 88, 250),
                ("GATE-07", "Gate 7", "East Main Exit Plaza Gate", "ZONE-H", [78.4675, 17.4125], "EXIT", 98, 250),
                ("GATE-08", "Gate 8", "Emergency Transit Gate", "ZONE-J", [78.4590, 17.4175], "BOTH", 0, 100),
            ]
            for gcode, name, label, zcode, coords, direct, flow, cap in raw_gates:
                g = Gate(
                    gate_code=gcode,
                    name=name,
                    label=label,
                    zone_code=zcode,
                    coordinates=coords,
                    direction=direct,
                    status="open" if flow > 0 else "closed",
                    flow_rate=flow,
                    capacity=cap,
                )
                session.add(g)
            await session.flush()

        # 6. Seed Cameras (100 General/Crowd + 16 FRS)
        # 6. Seed Camera (Single Main Camera)
        existing_cams = (await session.execute(select(Camera))).scalars().all()
        if not existing_cams:
            logger.info("Seeding 1 Main Camera...")
            cam = Camera(
                camera_code="CAM-KHB-001",
                name="Khairatabad Main Camera",
                label="Khairatabad Ganesh Main Idol View",
                camera_type="CROWD",
                zone_code="ZONE-A",
                coordinates=[78.4627, 17.4177],
                status="online",
                ai_status="online",
                is_frs_camera=True,
                is_ptz=False,
                resolution="1080p",
                fps=24,
                latency_ms=35,
                packet_loss_pct=0.0,
                people_count=0,
            )
            session.add(cam)
            await session.flush()

        # 7. Seed FRS Reference Profiles & Candidate Detections
        existing_frs = (await session.execute(select(FRSReferenceProfile))).scalars().all()
        if not existing_frs:
            logger.info("Seeding FRS Reference Profiles and Candidate Detections...")
            ref_profiles = [
                FRSReferenceProfile(
                    reference_id="WL-00281",
                    display_name="Demo Watchlist Person 042",
                    category="Authorized Watchlist",
                    status="ACTIVE",
                    reference_image_path="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'><rect width='160' height='160' fill='%231f293d'/><circle cx='80' cy='60' r='36' fill='%23d29922'/><path d='M30 145 C30 100 130 100 130 145 Z' fill='%23d29922'/></svg>",
                    last_updated_date="10 Sep 2026",
                ),
                FRSReferenceProfile(
                    reference_id="WL-00109",
                    display_name="Demo Case Subject 109",
                    category="Authorized Watchlist",
                    status="ACTIVE",
                    reference_image_path="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'><rect width='160' height='160' fill='%231f293d'/><circle cx='80' cy='60' r='36' fill='%2358a6ff'/><path d='M30 145 C30 100 130 100 130 145 Z' fill='%2358a6ff'/></svg>",
                    last_updated_date="08 Sep 2026",
                ),
            ]
            for rp in ref_profiles:
                session.add(rp)
            await session.flush()

            # Seed Candidates
            cands = [
                FRSCandidate(
                    candidate_code="FRS-EVT-00042",
                    camera_code="FRS-KHB-007",
                    camera_name="Main Entry FRS Camera 07",
                    zone_code="ZONE-A",
                    location="North Gate 1 Approach",
                    reference_profile_id=ref_profiles[0].id,
                    detected_image_path="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'><rect width='160' height='160' fill='%230d1117'/><circle cx='80' cy='60' r='36' fill='%23f85149'/><path d='M30 145 C30 100 130 100 130 145 Z' fill='%23f85149'/></svg>",
                    match_score=94.2,
                    status="PENDING_REVIEW",
                    review_required=True,
                    priority="HIGH",
                    image_quality="High (94%)",
                    timeline=[
                        {"time": "19:42:18", "event": "Face detected by FRS Camera 07"},
                        {"time": "19:42:19", "event": "High-confidence biometric feature match generated (94.2%)"},
                        {"time": "19:42:20", "event": "Candidate flagged — dispatched to Human Review Queue"},
                    ],
                ),
                FRSCandidate(
                    candidate_code="FRS-EVT-00039",
                    camera_code="FRS-KHB-003",
                    camera_name="South Approach FRS Camera 03",
                    zone_code="ZONE-E",
                    location="South Queue Gate 6",
                    reference_profile_id=ref_profiles[1].id,
                    detected_image_path="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'><rect width='160' height='160' fill='%230d1117'/><circle cx='80' cy='60' r='36' fill='%2358a6ff'/><path d='M30 145 C30 100 130 100 130 145 Z' fill='%2358a6ff'/></svg>",
                    match_score=87.6,
                    status="PENDING_REVIEW",
                    review_required=True,
                    priority="MEDIUM",
                    image_quality="Good (88%)",
                    timeline=[
                        {"time": "19:15:02", "event": "Face detected by FRS Camera 03"},
                        {"time": "19:15:03", "event": "Match score 87.6% generated"},
                    ],
                ),
            ]
            for c in cands:
                session.add(c)
            await session.flush()

        # 8. Seed Missing Persons
        existing_mp = (await session.execute(select(MissingPersonCase))).scalars().all()
        if not existing_mp:
            logger.info("Seeding Missing Persons cases...")
            mp_cases = [
                MissingPersonCase(
                    case_code="MP-2026-0042",
                    name="Demo Person 042",
                    age=9,
                    gender="Male",
                    reported_at=datetime.now(timezone.utc) - timedelta(minutes=75),
                    last_seen_time=datetime.now(timezone.utc) - timedelta(minutes=95),
                    last_known_zone_code="ZONE-A",
                    last_seen_camera_code="CAM-KHB-002",
                    description="Wearing yellow t-shirt, blue denim shorts, white sneakers.",
                    status="searching",
                    priority="HIGH",
                    candidate_matches=["FRS-EVT-00041"],
                    notes="Reported separated from parents near North Gate 1 food court.",
                ),
                MissingPersonCase(
                    case_code="MP-2026-0038",
                    name="Demo Person 038",
                    age=72,
                    gender="Female",
                    reported_at=datetime.now(timezone.utc) - timedelta(minutes=140),
                    last_seen_time=datetime.now(timezone.utc) - timedelta(minutes=160),
                    last_known_zone_code="ZONE-D",
                    last_seen_camera_code="CAM-KHB-026",
                    description="Wearing green cotton saree, carrying walking stick, speaks Telugu only.",
                    status="searching",
                    priority="MEDIUM",
                    candidate_matches=[],
                    notes="Senior citizen separated from family group during evening aarti rush.",
                ),
            ]
            for mp in mp_cases:
                session.add(mp)
            await session.flush()

        # 9. Seed Alerts
        existing_alerts = (await session.execute(select(Alert))).scalars().all()
        if not existing_alerts:
            logger.info("Seeding 20+ Operational Alerts...")
            raw_alerts = [
                ("ALT-0001", "crowd_density", "CRITICAL CROWD DENSITY", "critical", "Zone A at 96% Capacity", "North Gate 1 approach experiencing acute congestion.", "ZONE-A", "CAM-KHB-001"),
                ("ALT-0002", "queue", "QUEUE OVERFLOW", "critical", "Queue 1 Wait Time > 35 mins", "Processing rate reduced at North Gate. Queue extending past barricade.", "ZONE-A", "CAM-KHB-003"),
                ("ALT-0003", "bottleneck", "BOTTLENECK DETECTED", "high", "Transit Passage B-C Restricted", "Flow rate dropped below 20 persons/min at connecting corridor.", "ZONE-B", "CAM-KHB-012"),
                ("ALT-0004", "reverse_flow", "REVERSE FLOW DETECTED", "high", "Counter-flow at East Exit Plaza", "Pilgrims attempting to enter through designated exit corridor.", "ZONE-H", "CAM-KHB-071"),
                ("ALT-0005", "person_down", "PERSON DOWN / MEDICAL", "high", "Fall Incident Near Laddu Counter", "AI detected stationary person on ground. Nearby crowd pausing.", "ZONE-D", "CAM-KHB-033"),
                ("ALT-0006", "camera_offline", "CAMERA OFFLINE", "medium", "Camera CAM-KHB-013 Offline", "No video signal received for > 90 seconds. Field technician alerted.", "ZONE-B", "CAM-KHB-013"),
                ("ALT-0007", "frs_candidate", "FRS WATCHLIST CANDIDATE", "high", "Possible Match (94.2%) at Main Entry", "Candidate detection requires immediate authorized human review.", "ZONE-A", "FRS-KHB-007"),
                ("ALT-0008", "missing_person", "MISSING PERSON SIGHTING", "high", "Candidate match for Case MP-2026-0042", "High-confidence detection at North Gate 1 food court camera.", "ZONE-A", "CAM-KHB-002"),
                ("ALT-0009", "medical", "HEAT EXHAUSTION REPORT", "medium", "Medical assistance requested at Zone E", "First aid volunteer reported pilgrim needing hydration / stretcher.", "ZONE-E", "CAM-KHB-045"),
                ("ALT-0010", "traffic", "PARKING APPROACH SLOWDOWN", "low", "North-West Parking at 88% Capacity", "Inflow diverting towards secondary bypass road.", "ZONE-J", "CAM-KHB-091"),
            ]
            for acode, atype, alabel, asev, atitle, amsg, zc, cc in raw_alerts:
                a = Alert(
                    alert_code=acode,
                    type=atype,
                    type_label=alabel,
                    severity=asev,
                    title=atitle,
                    message=amsg,
                    zone_code=zc,
                    camera_code=cc,
                    status="active",
                    acknowledged=False,
                )
                session.add(a)
            await session.flush()

        # 10. Seed Incidents
        existing_incidents = (await session.execute(select(Incident))).scalars().all()
        if not existing_incidents:
            logger.info("Seeding Incidents...")
            raw_incidents = [
                ("INC-2026-0001", "crowd_surge", "Crowd Surge", "critical", "Darshan Queue Surge at North Gate 1", "Sudden surge of ~800 devotees breaking intermediate queue partition.", "North Gate 1 approach", "ZONE-A", ["CAM-KHB-001", "CAM-KHB-003"], "responding", "UNIT-01", "Sector 1 Quick Response Team", ["19:35 — AI crowd surge detection trigger", "19:36 — Acknowledged by Control Desk", "19:37 — Unit 01 dispatched to North Gate"]),
                ("INC-2026-0002", "medical_emergency", "Medical Emergency", "high", "Senior Citizen Collapse", "Female devotee (approx 68y) collapsed due to dehydration near prasadam counter.", "Zone D Laddu Counter 4", "ZONE-D", ["CAM-KHB-033"], "assigned", "MED-02", "Medical Response Team 2", ["19:40 — Alert acknowledged", "19:41 — Team MED-02 dispatched"]),
            ]
            for icode, itype, ilbl, isev, ititle, idesc, iloc, zc, cams, stat, ateam, ateamlbl, tmline in raw_incidents:
                inc = Incident(
                    incident_code=icode,
                    type=itype,
                    type_label=ilbl,
                    severity=isev,
                    title=ititle,
                    description=idesc,
                    location=iloc,
                    zone_code=zc,
                    cameras=cams,
                    status=stat,
                    assigned_team=ateam,
                    assigned_team_label=ateamlbl,
                    timeline=tmline,
                )
                session.add(inc)
            await session.flush()

        # 11. Seed Operations (Police & Medical Units, Emergency Corridors)
        existing_police = (await session.execute(select(PoliceUnit))).scalars().all()
        if not existing_police:
            logger.info("Seeding Police & Medical Units...")
            for pi in range(1, 21):
                p = PoliceUnit(
                    unit_code=f"UNIT-{pi:02d}",
                    name=f"Sector {((pi-1)%6)+1} QRT Patrol {pi:02d}",
                    zone_code=f"ZONE-{chr(65 + ((pi-1)%12))}",
                    location=f"Post {pi:02d} Corridor",
                    status="busy" if pi in (1, 4) else "available",
                    personnel=4,
                    contact=f"Ch-{((pi-1)%4)+1}",
                )
                session.add(p)

            for mi in range(1, 9):
                m = MedicalUnit(
                    team_code=f"MED-{mi:02d}",
                    name=f"First Aid & Paramedic Team {mi:02d}",
                    location=f"Medical Booth {mi:02d}",
                    status="busy" if mi == 2 else "available",
                    ambulance=True,
                    contact=f"MED-{mi}",
                )
                session.add(m)

            routes = [
                EmergencyRoute(
                    route_code="ROUTE-01",
                    name="North Gate to NIMS Hospital",
                    description="Primary trauma corridor via Khairatabad Flyover",
                    status="clear",
                    estimated_time="4 min",
                    coordinates=[[78.4610, 17.4190], [78.4650, 17.4220], [78.4710, 17.4280]],
                ),
                EmergencyRoute(
                    route_code="ROUTE-02",
                    name="East Exit to Gandhi Hospital",
                    description="Secondary corridor via Lower Tank Bund Road",
                    status="congested",
                    obstruction="Slow traffic near Secretariat Junction",
                    estimated_time="9 min",
                    coordinates=[[78.4715, 17.4165], [78.4780, 17.4200], [78.4850, 17.4250]],
                ),
            ]
            for r in routes:
                session.add(r)

        await session.commit()
        logger.info("Seed data successfully committed to database main_crowd_ai!")


if __name__ == "__main__":
    asyncio.run(seed_data())
