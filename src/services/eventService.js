// Event & Site Service — Multi-Event Command Center
import apiClient from "./apiClient";

export const eventService = {
  // Events
  async getEvents() {
    const res = await apiClient.get("/api/v1/events");
    return res.data || [];
  },

  async getCurrentEvent() {
    const res = await apiClient.get("/api/v1/events/current");
    return res.data;
  },

  async getEvent(id) {
    const res = await apiClient.get(`/api/v1/events/${id}`);
    return res.data;
  },

  async createEvent(data) {
    const res = await apiClient.post("/api/v1/events", data);
    return res.data;
  },

  async updateEvent(id, data) {
    const res = await apiClient.put(`/api/v1/events/${id}`, data);
    return res.data;
  },

  async archiveEvent(id) {
    const res = await apiClient.post(`/api/v1/events/${id}/archive`);
    return res.data;
  },

  // Sites
  async getSites(eventId = null) {
    const url = eventId ? `/api/v1/sites?event_id=${eventId}` : "/api/v1/sites";
    const res = await apiClient.get(url);
    return res.data || [];
  },

  async getSite(id) {
    const res = await apiClient.get(`/api/v1/sites/${id}`);
    return res.data;
  },

  async createSite(data) {
    const res = await apiClient.post("/api/v1/sites", data);
    return res.data;
  },

  async updateSite(id, data) {
    const res = await apiClient.put(`/api/v1/sites/${id}`, data);
    return res.data;
  },

  async deleteSite(id) {
    const res = await apiClient.delete(`/api/v1/sites/${id}`);
    return res.data;
  },

  // Event Access
  async getEventUsers(eventId) {
    const res = await apiClient.get(`/api/v1/events/${eventId}/access`);
    return res.data || [];
  },

  async grantEventUser(eventId, data) {
    const res = await apiClient.post(`/api/v1/events/${eventId}/access`, data);
    return res.data;
  },

  async revokeEventUser(eventId, userId) {
    const res = await apiClient.delete(`/api/v1/events/${eventId}/access/${userId}`);
    return res.data;
  },

  async getUserSiteAccess(eventId, userId) {
    const res = await apiClient.get(`/api/v1/events/${eventId}/access/${userId}/sites`);
    return res.data || [];
  },

  async setUserSiteAccess(eventId, data) {
    const res = await apiClient.post(`/api/v1/events/${eventId}/access/sites`, data);
    return res.data;
  },
};