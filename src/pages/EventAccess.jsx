import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useEventStore } from "../store/useEventStore";
import { eventService } from "../services/eventService";
import apiClient from "../services/apiClient";

export default function EventAccess() {
  const { eventId } = useParams();
  const { events } = useEventStore();
  const currentEvent = events.find((e) => e.id === eventId);

  const [accessList, setAccessList] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showGrantModal, setShowGrantModal] = useState(false);
  const [showSitesModal, setShowSitesModal] = useState(false);
  const [selectedUserAccess, setSelectedUserAccess] = useState(null);
  const [userSites, setUserSites] = useState([]);
  const [eventSites, setEventSites] = useState([]);
  const [selectedSiteIds, setSelectedSiteIds] = useState(new Set());

  const [grantForm, setGrantForm] = useState({
    user_id: "",
    access_role: "VIEWER",
  });

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [accRes, usersRes, sitesRes] = await Promise.all([
        eventService.getEventUsers(eventId),
        apiClient.get("/api/v1/users").then((r) => r.data || []),
        eventService.getSites(eventId),
      ]);
      setAccessList(accRes);
      setAllUsers(usersRes);
      setEventSites(sitesRes);
    } catch (err) {
      console.error("Failed to load access list:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (eventId) {
      loadData();
    }
  }, [eventId]);

  const handleGrant = async (e) => {
    e.preventDefault();
    try {
      await eventService.grantEventUser(eventId, {
        user_id: grantForm.user_id,
        event_id: eventId,
        access_role: grantForm.access_role,
      });
      setShowGrantModal(false);
      await loadData();
    } catch (err) {
      alert("Failed to grant access: " + (err.response?.data?.detail?.message || err.message));
    }
  };

  const handleRevoke = async (userId, username) => {
    if (!window.confirm(`Revoke access for user "${username}" from this event?`)) return;
    try {
      await eventService.revokeEventUser(eventId, userId);
      await loadData();
    } catch (err) {
      alert("Failed to revoke: " + err.message);
    }
  };

  const openSitesModal = async (acc) => {
    setSelectedUserAccess(acc);
    try {
      const existing = await eventService.getUserSiteAccess(eventId, acc.user_id);
      setSelectedSiteIds(new Set(existing.map((s) => s.site_id)));
      setShowSitesModal(true);
    } catch (err) {
      alert("Failed to load user site access: " + err.message);
    }
  };

  const handleSaveSites = async () => {
    try {
      await eventService.setUserSiteAccess(eventId, {
        user_id: selectedUserAccess.user_id,
        site_ids: Array.from(selectedSiteIds),
      });
      setShowSitesModal(false);
      alert("Site permissions updated successfully");
    } catch (err) {
      alert("Failed to save site permissions: " + err.message);
    }
  };

  return (
    <div className="cc-page" style={{ padding: "24px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <div className="d-flex align-items-center gap-2 mb-1">
            <Link to="/events" className="btn btn-outline-secondary btn-sm" style={{ padding: "2px 8px" }}>
              <i className="bi bi-arrow-left me-1" />
              Events
            </Link>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--cc-text-primary)" }}>
              <i className="bi bi-shield-lock-fill me-2" style={{ color: "var(--cc-accent)" }} />
              Event Access & RBAC: {currentEvent?.name || "Event"}
            </h2>
          </div>
          <p style={{ margin: "4px 0 0", color: "var(--cc-text-muted)", fontSize: 13 }}>
            Manage officer access privileges, command roles, and site-level isolation boundaries.
          </p>
        </div>

        <button
          className="btn btn-primary btn-sm d-flex align-items-center gap-2"
          onClick={() => setShowGrantModal(true)}
          style={{ padding: "8px 16px", fontWeight: 600 }}
        >
          <i className="bi bi-person-plus-fill" />
          Assign User Access
        </button>
      </div>

      {/* Access Table */}
      <div className="card" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)", borderRadius: 12 }}>
        <div className="table-responsive">
          <table className="table table-hover mb-0" style={{ color: "var(--cc-text-primary)" }}>
            <thead style={{ background: "rgba(255,255,255,0.02)", borderBottomColor: "var(--cc-border)" }}>
              <tr>
                <th style={{ padding: "12px 16px", fontSize: 12, color: "var(--cc-text-muted)" }}>User</th>
                <th style={{ padding: "12px 16px", fontSize: 12, color: "var(--cc-text-muted)" }}>Username</th>
                <th style={{ padding: "12px 16px", fontSize: 12, color: "var(--cc-text-muted)" }}>Event Access Role</th>
                <th style={{ padding: "12px 16px", fontSize: 12, color: "var(--cc-text-muted)" }}>Status</th>
                <th style={{ padding: "12px 16px", fontSize: 12, color: "var(--cc-text-muted)" }}>Granted By</th>
                <th style={{ padding: "12px 16px", fontSize: 12, color: "var(--cc-text-muted)", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan="6" className="text-center py-4" style={{ color: "var(--cc-text-muted)" }}>
                    Loading user access records...
                  </td>
                </tr>
              ) : accessList.length === 0 ? (
                <tr>
                  <td colSpan="6" className="text-center py-4" style={{ color: "var(--cc-text-muted)" }}>
                    No specific user permissions assigned.
                  </td>
                </tr>
              ) : (
                accessList.map((acc) => (
                  <tr key={acc.id} style={{ borderColor: "var(--cc-border)" }}>
                    <td style={{ padding: "14px 16px", fontWeight: 600 }}>{acc.full_name || "Unknown"}</td>
                    <td style={{ padding: "14px 16px", fontFamily: "var(--cc-font-mono)", fontSize: 12 }}>
                      {acc.username}
                    </td>
                    <td style={{ padding: "14px 16px" }}>
                      <span className="badge bg-primary" style={{ fontSize: 11 }}>
                        {acc.access_role}
                      </span>
                    </td>
                    <td style={{ padding: "14px 16px" }}>
                      <span className="badge bg-success" style={{ fontSize: 10 }}>
                        ACTIVE
                      </span>
                    </td>
                    <td style={{ padding: "14px 16px", color: "var(--cc-text-muted)", fontSize: 12 }}>
                      {acc.granted_by || "System"}
                    </td>
                    <td style={{ padding: "14px 16px", textAlign: "right" }}>
                      <button
                        className="btn btn-outline-secondary btn-sm me-2"
                        onClick={() => openSitesModal(acc)}
                        title="Configure site boundaries"
                      >
                        <i className="bi bi-geo-alt me-1" />
                        Sites
                      </button>
                      <button
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => handleRevoke(acc.user_id, acc.username)}
                        title="Revoke access"
                      >
                        <i className="bi bi-x-circle" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Grant Access Modal */}
      {showGrantModal && (
        <div className="modal show d-block" style={{ background: "rgba(0,0,0,0.7)", zIndex: 1050 }} tabIndex="-1">
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
              <div className="modal-header" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title text-white">Assign User to Event</h5>
                <button type="button" className="btn-close btn-close-white" onClick={() => setShowGrantModal(false)} />
              </div>
              <form onSubmit={handleGrant}>
                <div className="modal-body p-4">
                  <div className="mb-3">
                    <label className="form-label text-muted small">Select Officer / User</label>
                    <select
                      className="form-select"
                      required
                      value={grantForm.user_id}
                      onChange={(e) => setGrantForm({ ...grantForm, user_id: e.target.value })}
                    >
                      <option value="">-- Choose User --</option>
                      {allUsers.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.full_name} ({u.username})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="mb-3">
                    <label className="form-label text-muted small">Event Access Role</label>
                    <select
                      className="form-select"
                      value={grantForm.access_role}
                      onChange={(e) => setGrantForm({ ...grantForm, access_role: e.target.value })}
                    >
                      <option value="COMMANDER">COMMANDER (Full event control & dispatch)</option>
                      <option value="OPERATOR">OPERATOR (Cameras, crowd, queues)</option>
                      <option value="FRS_OPERATOR">FRS_OPERATOR (Face recognition & missing persons)</option>
                      <option value="VIEWER">VIEWER (Read-only monitoring)</option>
                    </select>
                  </div>
                </div>
                <div className="modal-footer" style={{ borderColor: "var(--cc-border)" }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowGrantModal(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary btn-sm">
                    Confirm Access
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Sites Restriction Modal */}
      {showSitesModal && (
        <div className="modal show d-block" style={{ background: "rgba(0,0,0,0.7)", zIndex: 1050 }} tabIndex="-1">
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
              <div className="modal-header" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title text-white">
                  Site Isolation for {selectedUserAccess?.full_name}
                </h5>
                <button type="button" className="btn-close btn-close-white" onClick={() => setShowSitesModal(false)} />
              </div>
              <div className="modal-body p-4">
                <p style={{ fontSize: 12, color: "var(--cc-text-muted)", marginBottom: 16 }}>
                  Select the physical operational sites this officer is authorized to view and control.
                  If no specific sites are selected, the user will have access to all sites under this event.
                </p>

                <div className="d-flex flex-column gap-2">
                  {eventSites.map((s) => {
                    const checked = selectedSiteIds.has(s.id);
                    return (
                      <label
                        key={s.id}
                        className="p-2 d-flex align-items-center gap-3"
                        style={{
                          background: "var(--cc-bg-secondary, rgba(255,255,255,0.03))",
                          border: "1px solid var(--cc-border)",
                          borderRadius: 8,
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          className="form-check-input mt-0"
                          checked={checked}
                          onChange={() => {
                            const next = new Set(selectedSiteIds);
                            if (checked) next.delete(s.id);
                            else next.add(s.id);
                            setSelectedSiteIds(next);
                          }}
                        />
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 13, color: "var(--cc-text-primary)" }}>
                            {s.site_name}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                            {s.site_code} • {s.location || "General Area"}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="modal-footer" style={{ borderColor: "var(--cc-border)" }}>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowSitesModal(false)}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary btn-sm" onClick={handleSaveSites}>
                  Save Site Restrictions
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}