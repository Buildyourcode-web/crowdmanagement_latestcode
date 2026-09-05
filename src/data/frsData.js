// DEMO DATA ONLY — FRS Module Mock Data for Khairatabad Ganesh Festival 2026
// FRS results are ALWAYS "POSSIBLE MATCH — REQUIRES HUMAN REVIEW"
// Strictly fictional personas and generated portrait graphics for UI demonstration.

const now = Date.now();
const t = (offsetMinutes) => new Date(now - offsetMinutes * 60 * 1000).toISOString();

// SVG Portrait generator for realistic mock detected crops vs HD reference photos
export function generateFaceAvatar(seed, isReference = false, bgHue = 210) {
  const skinTones = ["#ffd0b0", "#f2be9b", "#e0ab8b", "#d09b7b", "#c58a68", "#a56a48"];
  const hairColors = ["#1a1a1a", "#2c1e18", "#3d2817", "#4a3b32", "#1e242b"];
  const skin = skinTones[seed % skinTones.length];
  const hair = hairColors[(seed * 3) % hairColors.length];
  const shirt = `hsl(${(seed * 67) % 360}, 50%, ${isReference ? "40%" : "30%"})`;
  const bg = isReference ? "#1a2332" : "#0d141e";

  return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 240" width="100%" height="100%">
    <rect width="200" height="240" fill="${bg}"/>
    ${!isReference ? `<rect x="15" y="15" width="170" height="210" fill="none" stroke="rgba(2,132,199,0.7)" stroke-width="1.5" stroke-dasharray="6,3"/>` : ""}
    ${!isReference ? `<circle cx="100" cy="110" r="62" fill="none" stroke="rgba(2,132,199,0.3)" stroke-width="1"/>` : ""}
    <path d="M 40 240 Q 100 175 160 240 Z" fill="${shirt}"/>
    <rect x="85" y="145" width="30" height="35" fill="${skin}"/>
    <!-- Head -->
    <ellipse cx="100" cy="105" rx="42" ry="52" fill="${skin}"/>
    <!-- Hair -->
    <path d="M 58 100 Q 58 55 100 55 Q 142 55 142 100 Q 130 75 100 78 Q 70 75 58 100 Z" fill="${hair}"/>
    <!-- Eyes -->
    <ellipse cx="85" cy="102" rx="4.5" ry="3" fill="#1e293b"/>
    <ellipse cx="115" cy="102" rx="4.5" ry="3" fill="#1e293b"/>
    <circle cx="86" cy="101" r="1" fill="#fff"/>
    <circle cx="116" cy="101" r="1" fill="#fff"/>
    <!-- Eyebrows -->
    <path d="M 76 94 Q 85 91 94 94" stroke="${hair}" stroke-width="2.5" fill="none"/>
    <path d="M 106 94 Q 115 91 124 94" stroke="${hair}" stroke-width="2.5" fill="none"/>
    <!-- Nose -->
    <path d="M 100 102 L 97 118 L 104 118" stroke="rgba(0,0,0,0.25)" stroke-width="2" fill="none"/>
    <!-- Mouth -->
    <path d="M 90 132 Q 100 138 110 132" stroke="#993333" stroke-width="2" fill="none"/>
    ${isReference ? `<text x="100" y="230" text-anchor="middle" fill="#94a3b8" font-size="9" font-family="monospace">HD REFERENCE</text>` : ""}
    ${!isReference ? `<text x="25" y="32" fill="#38bdf8" font-size="8" font-family="monospace">CAM-CROP [Q: ${(85 + (seed % 12))}%]</text>` : ""}
  </svg>`;
}

export const FRS_DASHBOARD_KPIS = {
  camerasOnline: 15,
  camerasTotal: 16,
  detectionsToday: 1842,
  possibleMatches: 7,
  pendingReview: 3,
  dismissed: 4,
  activeCases: 2,
  processingFps: 24,
  avgLatencyMs: 38,
};

export const FRS_CAMERAS = [
  { id: "FRS-KHB-001", name: "Main Entry FRS Camera 01", location: "Khairatabad Main Entry Gate", zone: "ZONE-A", status: "online", fps: 24, latency: 36, faceDetections: 184, possibleMatches: 1, pendingReview: 0 },
  { id: "FRS-KHB-002", name: "North Gate FRS Camera 02", location: "Gate 1 North Approach", zone: "ZONE-A", status: "online", fps: 23, latency: 41, faceDetections: 142, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-003", name: "East Gate FRS Camera 03", location: "Gate 2 East Entry", zone: "ZONE-A", status: "online", fps: 24, latency: 38, faceDetections: 156, possibleMatches: 1, pendingReview: 1 },
  { id: "FRS-KHB-004", name: "Stage Approach FRS Camera 04", location: "Central Darshan Corridor", zone: "ZONE-B", status: "online", fps: 24, latency: 35, faceDetections: 210, possibleMatches: 1, pendingReview: 0 },
  { id: "FRS-KHB-005", name: "Main Idol Stage FRS Camera 05", location: "Main Stage Enclosure", zone: "ZONE-B", status: "online", fps: 22, latency: 45, faceDetections: 195, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-006", name: "Queue Area A FRS Camera 06", location: "Queue Barrier Line A", zone: "ZONE-C", status: "online", fps: 24, latency: 39, faceDetections: 178, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-007", name: "Main Entry FRS Camera 07", location: "Khairatabad Main Entry", zone: "ZONE-A", status: "online", fps: 24, latency: 38, faceDetections: 227, possibleMatches: 2, pendingReview: 1 },
  { id: "FRS-KHB-008", name: "South Viewing FRS Camera 08", location: "South Viewing Gallery Gate", zone: "ZONE-D", status: "online", fps: 23, latency: 40, faceDetections: 98, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-009", name: "Food Court Entry FRS Camera 09", location: "Prasadam & Food Court Entry", zone: "ZONE-E", status: "online", fps: 24, latency: 37, faceDetections: 114, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-010", name: "VIP Corridor FRS Camera 10", location: "VIP Enclosure Entry", zone: "ZONE-G", status: "online", fps: 24, latency: 34, faceDetections: 82, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-011", name: "South Exit FRS Camera 11", location: "South Procession Exit Gate", zone: "ZONE-H", status: "online", fps: 23, latency: 42, faceDetections: 165, possibleMatches: 1, pendingReview: 0 },
  { id: "FRS-KHB-012", name: "Media Stand FRS Camera 12", location: "Press & Media Enclosure", zone: "ZONE-I", status: "online", fps: 24, latency: 36, faceDetections: 45, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-013", name: "East Corridor FRS Camera 13", location: "East Entry Corridor Gate 4", zone: "ZONE-K", status: "online", fps: 24, latency: 39, faceDetections: 139, possibleMatches: 1, pendingReview: 1 },
  { id: "FRS-KHB-014", name: "West Corridor FRS Camera 14", location: "West Entry Corridor Gate 6", zone: "ZONE-L", status: "online", fps: 23, latency: 44, faceDetections: 108, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-015", name: "Emergency Staging FRS Camera 15", location: "Emergency Access Gate 8", zone: "ZONE-J", status: "online", fps: 24, latency: 35, faceDetections: 26, possibleMatches: 0, pendingReview: 0 },
  { id: "FRS-KHB-016", name: "Pedestrian Subway FRS Camera 16", location: "Metro Station Underpass", zone: "ZONE-A", status: "offline", fps: 0, latency: null, faceDetections: 0, possibleMatches: 0, pendingReview: 0 },
];

export const FRS_DETECTIONS = [
  {
    id: "FRS-EVT-00042",
    detectedImage: generateFaceAvatar(42, false),
    referenceImage: generateFaceAvatar(42, true),
    referenceName: "Demo Watchlist Person 042",
    referenceId: "WL-00281",
    category: "Authorized Watchlist",
    referenceStatus: "ACTIVE",
    lastUpdated: "10 Sep 2026",
    matchScore: 94.2,
    cameraId: "FRS-KHB-007",
    cameraName: "Main Entry FRS Camera 07",
    location: "Khairatabad Main Entry",
    zone: "ZONE-A",
    timestamp: t(4),
    dateStr: "14 Sep 2026",
    timeStr: "19:42:18",
    status: "PENDING_REVIEW",
    reviewRequired: true,
    priority: "HIGH",
    imageQuality: "High (94%)",
    timeline: [
      { time: "19:42:18", event: "Candidate face detected by AI pipeline", actor: "FRS-KHB-007" },
      { time: "19:42:20", event: "Candidate vector generated & feature extraction complete", actor: "AI Edge Engine" },
      { time: "19:42:21", event: "Possible reference match generated (Confidence: 94.2%)", actor: "Watchlist Matcher" },
      { time: "19:43:05", event: "Alert dispatched to Command Console — Pending Human Review", actor: "System Router" },
    ],
    officerNotes: "",
    reviewedBy: null,
    reviewedAt: null,
  },
  {
    id: "FRS-EVT-00041",
    detectedImage: generateFaceAvatar(89, false),
    referenceImage: generateFaceAvatar(89, true),
    referenceName: "Demo Missing Person 089",
    referenceId: "MP-00412",
    category: "Missing Person Registry",
    referenceStatus: "ACTIVE_SEARCH",
    lastUpdated: "13 Sep 2026",
    matchScore: 88.6,
    cameraId: "FRS-KHB-013",
    cameraName: "East Corridor FRS Camera 13",
    location: "East Entry Corridor Gate 4",
    zone: "ZONE-K",
    timestamp: t(14),
    dateStr: "14 Sep 2026",
    timeStr: "19:32:05",
    status: "PENDING_REVIEW",
    reviewRequired: true,
    priority: "HIGH",
    imageQuality: "Good (88%)",
    timeline: [
      { time: "19:32:05", event: "Candidate face detected", actor: "FRS-KHB-013" },
      { time: "19:32:07", event: "Candidate processed", actor: "AI Edge Engine" },
      { time: "19:32:08", event: "Possible MP candidate match generated (88.6%)", actor: "MP Matcher" },
    ],
    officerNotes: "",
    reviewedBy: null,
    reviewedAt: null,
  },
  {
    id: "FRS-EVT-00040",
    detectedImage: generateFaceAvatar(104, false),
    referenceImage: generateFaceAvatar(104, true),
    referenceName: "Demo Watchlist Person 104",
    referenceId: "WL-00192",
    category: "Authorized Watchlist",
    referenceStatus: "ACTIVE",
    lastUpdated: "08 Sep 2026",
    matchScore: 91.7,
    cameraId: "FRS-KHB-003",
    cameraName: "East Gate FRS Camera 03",
    location: "Gate 2 East Entry",
    zone: "ZONE-A",
    timestamp: t(28),
    dateStr: "14 Sep 2026",
    timeStr: "19:18:40",
    status: "PENDING_REVIEW",
    reviewRequired: true,
    priority: "HIGH",
    imageQuality: "High (91%)",
    timeline: [
      { time: "19:18:40", event: "Candidate face detected", actor: "FRS-KHB-003" },
      { time: "19:18:42", event: "Possible reference match generated (91.7%)", actor: "Watchlist Matcher" },
    ],
    officerNotes: "",
    reviewedBy: null,
    reviewedAt: null,
  },
  {
    id: "FRS-EVT-00039",
    detectedImage: generateFaceAvatar(314, false),
    referenceImage: generateFaceAvatar(314, true),
    referenceName: "Demo Watchlist Person 314",
    referenceId: "WL-00314",
    category: "Authorized Watchlist",
    referenceStatus: "ACTIVE",
    lastUpdated: "11 Sep 2026",
    matchScore: 96.1,
    cameraId: "FRS-KHB-011",
    cameraName: "South Exit FRS Camera 11",
    location: "South Procession Exit Gate",
    zone: "ZONE-H",
    timestamp: t(52),
    dateStr: "14 Sep 2026",
    timeStr: "18:55:12",
    status: "POSSIBLE_MATCH",
    reviewRequired: false,
    priority: "HIGH",
    imageQuality: "Excellent (97%)",
    timeline: [
      { time: "18:55:12", event: "Candidate face detected", actor: "FRS-KHB-011" },
      { time: "18:55:15", event: "Match score 96.1% generated", actor: "Watchlist Matcher" },
      { time: "18:56:40", event: "Officer opened candidate review", actor: "Cmd Officer Sharma (CS)" },
      { time: "18:58:10", event: "Decision recorded: POSSIBLE MATCH — Notified Field Sector 4", actor: "Cmd Officer Sharma (CS)" },
    ],
    officerNotes: "Physical features match reference record. Field unit alerted to keep discreet observation.",
    reviewedBy: "Cmd Officer Sharma (CS)",
    reviewedAt: "18:58:10",
  },
  {
    id: "FRS-EVT-00038",
    detectedImage: generateFaceAvatar(122, false),
    referenceImage: generateFaceAvatar(122, true),
    referenceName: "Demo Watchlist Person 122",
    referenceId: "WL-00122",
    category: "Authorized Watchlist",
    referenceStatus: "ACTIVE",
    lastUpdated: "05 Sep 2026",
    matchScore: 78.4,
    cameraId: "FRS-KHB-004",
    cameraName: "Stage Approach FRS Camera 04",
    location: "Central Darshan Corridor",
    zone: "ZONE-B",
    timestamp: t(85),
    dateStr: "14 Sep 2026",
    timeStr: "18:22:30",
    status: "DISMISSED",
    reviewRequired: false,
    priority: "MEDIUM",
    imageQuality: "Fair (76%)",
    timeline: [
      { time: "18:22:30", event: "Candidate detected", actor: "FRS-KHB-004" },
      { time: "18:23:10", event: "Officer opened review", actor: "Inspector Rao (IR)" },
      { time: "18:24:05", event: "Decision recorded: NOT A MATCH / DISMISSED", actor: "Inspector Rao (IR)" },
    ],
    officerNotes: "Visual inspection confirms distinct facial structure and ear geometry. False trigger cleared.",
    reviewedBy: "Inspector Rao (IR)",
    reviewedAt: "18:24:05",
  },
  {
    id: "FRS-EVT-00037",
    detectedImage: generateFaceAvatar(56, false),
    referenceImage: generateFaceAvatar(56, true),
    referenceName: "Demo Watchlist Person 056",
    referenceId: "WL-00056",
    category: "Authorized Watchlist",
    referenceStatus: "ACTIVE",
    lastUpdated: "02 Sep 2026",
    matchScore: 84.3,
    cameraId: "FRS-KHB-001",
    cameraName: "Main Entry FRS Camera 01",
    location: "Khairatabad Main Entry Gate",
    zone: "ZONE-A",
    timestamp: t(120),
    dateStr: "14 Sep 2026",
    timeStr: "17:47:19",
    status: "DISMISSED",
    reviewRequired: false,
    priority: "MEDIUM",
    imageQuality: "Good (84%)",
    timeline: [
      { time: "17:47:19", event: "Candidate detected", actor: "FRS-KHB-001" },
      { time: "17:48:00", event: "Officer review complete: NOT A MATCH", actor: "Inspector Reddy" },
    ],
    officerNotes: "Subject wearing sunglasses created partial match artifact. Dismissed.",
    reviewedBy: "Inspector Reddy",
    reviewedAt: "17:48:00",
  },
  {
    id: "FRS-EVT-00036",
    detectedImage: generateFaceAvatar(77, false),
    referenceImage: generateFaceAvatar(77, true),
    referenceName: "Demo Missing Person 077",
    referenceId: "MP-00077",
    category: "Missing Person Registry",
    referenceStatus: "RESOLVED",
    lastUpdated: "14 Sep 2026",
    matchScore: 92.4,
    cameraId: "FRS-KHB-007",
    cameraName: "Main Entry FRS Camera 07",
    location: "Khairatabad Main Entry",
    zone: "ZONE-A",
    timestamp: t(160),
    dateStr: "14 Sep 2026",
    timeStr: "17:07:44",
    status: "CLOSED",
    reviewRequired: false,
    priority: "HIGH",
    imageQuality: "High (92%)",
    timeline: [
      { time: "17:07:44", event: "Candidate detected", actor: "FRS-KHB-007" },
      { time: "17:09:12", event: "Officer confirmed possible match", actor: "Cmd Officer Sharma" },
      { time: "17:25:00", event: "Person safely reunited at Helpdesk Booth 2", actor: "Child Welfare Desk" },
    ],
    officerNotes: "Child located by Gate 1 helpdesk unit. Case successfully closed.",
    reviewedBy: "Cmd Officer Sharma",
    reviewedAt: "17:09:12",
  },
];
