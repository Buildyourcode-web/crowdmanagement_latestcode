// Location Service — Physical Location & Access Management
import apiClient from "./apiClient";

export const locationService = {
  // Send OTP verification code to registered email
  async sendVerificationCode(data) {
    const res = await apiClient.post("/api/v1/locations/send-verification-code", data);
    return res.data;
  },

  // Verify OTP code
  async verifyCode(data) {
    const res = await apiClient.post("/api/v1/locations/verify-code", data);
    return res.data;
  },

  // List all locations
  async getLocations() {
    const res = await apiClient.get("/api/v1/locations");
    return res.data || [];
  },

  // Get specific location
  async getLocation(id) {
    const res = await apiClient.get(`/api/v1/locations/${id}`);
    return res.data;
  },

  // Create new location
  async createLocation(data) {
    const res = await apiClient.post("/api/v1/locations", data);
    return res.data;
  },

  // Update location metadata
  async updateLocation(id, data) {
    const res = await apiClient.put(`/api/v1/locations/${id}`, data);
    return res.data;
  },

  // Verify location access code
  async verifyAccessCode(id, accessCode) {
    const res = await apiClient.post(`/api/v1/locations/${id}/verify-access`, {
      access_code: accessCode,
    });
    return res.data;
  },

  // Request recovery OTP for forgot access code
  async forgotAccessCode(id, email) {
    const res = await apiClient.post(`/api/v1/locations/${id}/forgot-access-code`, {
      email,
    });
    return res.data;
  },

  // Reset access code with verified OTP
  async resetAccessCode(id, data) {
    const res = await apiClient.post(`/api/v1/locations/${id}/reset-access-code`, data);
    return res.data;
  },

  // List festivals/events for a location
  async getLocationEvents(id) {
    const res = await apiClient.get(`/api/v1/locations/${id}/events`);
    return res.data || [];
  },

  // Add new festival under a location
  async createLocationEvent(id, data) {
    const res = await apiClient.post(`/api/v1/locations/${id}/events`, data);
    return res.data;
  },

  // Deliberately link existing event to location (Safeguard #1)
  async linkExistingEvent(locationId, eventId) {
    const res = await apiClient.post(`/api/v1/locations/${locationId}/link-event/${eventId}`);
    return res.data;
  },
};

export default locationService;
