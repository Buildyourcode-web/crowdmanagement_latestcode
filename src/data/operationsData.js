// DEMO DATA ONLY — Operations mock data for Khairatabad Ganesh Festival 2026

export const POLICE_UNITS = [
  { id: "UNIT-01", name: "Unit 01", type: "police", zone: "ZONE-A", location: "North Gate", status: "available", personnel: 4, contact: "Ch-1" },
  { id: "UNIT-02", name: "Unit 02", type: "police", zone: "ZONE-A", location: "Gate 1 Area", status: "available", personnel: 4, contact: "Ch-1" },
  { id: "UNIT-03", name: "Unit 03", type: "police", zone: "ZONE-A", location: "North Procession", status: "available", personnel: 4, contact: "Ch-1" },
  { id: "UNIT-04", name: "Unit 04", type: "police", zone: "ZONE-B", location: "Main Stage Perimeter", status: "responding", personnel: 6, contact: "Ch-2" },
  { id: "UNIT-05", name: "Unit 05", type: "police", zone: "ZONE-G", location: "VIP Zone", status: "available", personnel: 4, contact: "Ch-2" },
  { id: "UNIT-06", name: "Unit 06", type: "police", zone: "ZONE-B", location: "Gate 3 Area", status: "responding", personnel: 4, contact: "Ch-2" },
  { id: "UNIT-07", name: "Unit 07", type: "police", zone: "ZONE-C", location: "East Queue", status: "available", personnel: 4, contact: "Ch-3" },
  { id: "UNIT-08", name: "Unit 08", type: "police", zone: "ZONE-D", location: "South Viewing", status: "available", personnel: 4, contact: "Ch-3" },
  { id: "UNIT-09", name: "Unit 09", type: "police", zone: "ZONE-E", location: "Food Court", status: "available", personnel: 4, contact: "Ch-3" },
  { id: "UNIT-10", name: "Unit 10", type: "police", zone: "ZONE-F", location: "Parking North", status: "available", personnel: 4, contact: "Ch-4" },
  { id: "UNIT-11", name: "Unit 11", type: "police", zone: "ZONE-H", location: "South Route", status: "available", personnel: 4, contact: "Ch-4" },
  { id: "UNIT-12", name: "Unit 12", type: "police", zone: "ZONE-B", location: "Zone B — Crowd Control", status: "responding", personnel: 8, contact: "Ch-2" },
  { id: "UNIT-13", name: "Unit 13", type: "police", zone: "ZONE-K", location: "East Corridor", status: "available", personnel: 4, contact: "Ch-5" },
  { id: "UNIT-14", name: "Unit 14", type: "police", zone: "ZONE-L", location: "West Corridor", status: "available", personnel: 4, contact: "Ch-5" },
  { id: "UNIT-15", name: "Unit 15", type: "police", zone: "ZONE-J", location: "Emergency Area", status: "standby", personnel: 4, contact: "Ch-5" },
  { id: "UNIT-16", name: "Unit 16", type: "police", zone: "ZONE-A", location: "Gate 2 Area", status: "available", personnel: 4, contact: "Ch-1" },
  { id: "UNIT-17", name: "Unit 17", type: "police", zone: "ZONE-B", location: "Central Crowd", status: "responding", personnel: 6, contact: "Ch-2" },
  { id: "UNIT-18", name: "Unit 18", type: "police", zone: "ZONE-E", location: "Food Court West", status: "responding", personnel: 4, contact: "Ch-3" },
  { id: "UNIT-19", name: "Unit 19", type: "police", zone: "ZONE-H", location: "Gate 7", status: "available", personnel: 4, contact: "Ch-4" },
  { id: "UNIT-20", name: "Unit 20", type: "police", zone: "ZONE-I", location: "Media Zone", status: "available", personnel: 2, contact: "Ch-5" },
];

export const MEDICAL_TEAMS = [
  { id: "MED-TEAM-01", name: "Medical Team 1", zone: "ZONE-A", location: "North First Aid Post", status: "available", personnel: 3, ambulance: true, responseTime: "3 min", equipment: ["AED", "stretcher", "basic trauma"] },
  { id: "MED-TEAM-02", name: "Medical Team 2", zone: "ZONE-B", location: "Zone B — Active Incident", status: "responding", personnel: 4, ambulance: true, responseTime: "2 min", equipment: ["AED", "oxygen", "stretcher", "trauma kit"] },
  { id: "MED-TEAM-03", name: "Medical Team 3", zone: "ZONE-C", location: "East Queue Post", status: "available", personnel: 3, ambulance: false, responseTime: "5 min", equipment: ["AED", "basic trauma"] },
  { id: "MED-TEAM-04", name: "Medical Team 4", zone: "ZONE-D", location: "South First Aid Post", status: "available", personnel: 3, ambulance: false, responseTime: "4 min", equipment: ["AED", "stretcher", "basic trauma"] },
  { id: "MED-TEAM-05", name: "Medical Team 5", zone: "ZONE-E", location: "Food Court Medical", status: "available", personnel: 3, ambulance: true, responseTime: "3 min", equipment: ["AED", "oxygen", "stretcher"] },
  { id: "MED-TEAM-06", name: "Medical Team 6", zone: "ZONE-H", location: "South Route Post", status: "available", personnel: 3, ambulance: false, responseTime: "5 min", equipment: ["AED", "basic trauma"] },
  { id: "MED-TEAM-07", name: "Medical Team 7", zone: "ZONE-K", location: "East Corridor Post", status: "standby", personnel: 4, ambulance: true, responseTime: "3 min", equipment: ["AED", "oxygen", "stretcher", "trauma kit"] },
  { id: "MED-TEAM-08", name: "Medical Team 8", zone: "ZONE-J", location: "Emergency Staging", status: "available", personnel: 5, ambulance: true, responseTime: "2 min", equipment: ["AED", "oxygen", "stretcher", "ICU kit"] },
];

export const EMERGENCY_ROUTES = [
  { id: "ROUTE-A", name: "Route A", description: "North Entry to Main Stage — Primary ambulance route", status: "clear", zones: ["ZONE-F", "ZONE-A", "ZONE-B"], estimatedTime: "4 min" },
  { id: "ROUTE-B", name: "Route B", description: "East Corridor to Central — Secondary ambulance route", status: "partial", zones: ["ZONE-K", "ZONE-C", "ZONE-B"], estimatedTime: "7 min", obstruction: "Partial crowd obstruction at Zone C junction" },
  { id: "ROUTE-C", name: "Route C", description: "West Access Road to Emergency Zone", status: "blocked", zones: ["ZONE-L", "ZONE-J"], estimatedTime: null, obstruction: "Unauthorized vehicle — Traffic unit dispatched" },
  { id: "ROUTE-D", name: "Route D", description: "South Exit Route — Main stage evacuation", status: "clear", zones: ["ZONE-B", "ZONE-H", "ZONE-D"], estimatedTime: "6 min" },
  { id: "ROUTE-E", name: "Route E", description: "VIP Evacuation — Zone G to North Exit", status: "clear", zones: ["ZONE-G", "ZONE-F"], estimatedTime: "3 min" },
];

export default POLICE_UNITS;
