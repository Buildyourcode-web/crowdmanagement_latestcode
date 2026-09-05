// mockWebSocket.js — DISABLED
// Fake data generation has been removed.
// Real data is fetched directly from the backend REST API.
// This stub is kept to avoid breaking any residual imports.

class NoOpWebSocket {
  connect() {}
  disconnect() {}
  on() { return () => {}; }
  off() {}
}

const mockWS = new NoOpWebSocket();
export default mockWS;
