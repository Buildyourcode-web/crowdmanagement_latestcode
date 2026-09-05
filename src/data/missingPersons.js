// DEMO DATA ONLY — Missing Persons Mock Registry for Khairatabad Ganesh Festival 2026
const now = Date.now();
const t = (offsetMinutes) => new Date(now - offsetMinutes * 60 * 1000).toISOString();

export const MISSING_PERSONS = [
  {
    id: "MP-2026-0042",
    name: "Demo Person 042",
    age: 9,
    gender: "Male",
    reportedAt: t(75),
    lastSeenTime: t(95),
    lastKnownZone: "ZONE-A",
    lastSeenCamera: "CAM-KHB-002",
    description: "Wearing yellow t-shirt, blue denim shorts, white sneakers.",
    status: "searching",
    candidateMatches: ["FRS-EVT-00041"],
    notes: "Reported separated from parents near North Gate 1 food court. Field search teams alerted.",
  },
  {
    id: "MP-2026-0038",
    name: "Demo Person 038",
    age: 72,
    gender: "Female",
    reportedAt: t(140),
    lastSeenTime: t(160),
    lastKnownZone: "ZONE-D",
    lastSeenCamera: "CAM-KHB-026",
    description: "Wearing green cotton saree, carrying walking stick, speaks Telugu only.",
    status: "searching",
    candidateMatches: [],
    notes: "Senior citizen separated from family group during evening aarti rush.",
  },
  {
    id: "MP-2026-0029",
    name: "Demo Person 029",
    age: 12,
    gender: "Female",
    reportedAt: t(240),
    lastSeenTime: t(260),
    lastKnownZone: "ZONE-C",
    lastSeenCamera: "CAM-KHB-015",
    description: "Red dress, black backpack with school badge.",
    status: "found",
    candidateMatches: ["FRS-EVT-00036"],
    notes: "Located by Sector 3 helpdesk personnel. Safely reunited with guardian.",
  },
];

export default MISSING_PERSONS;
