import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useEventStore } from "../store/useEventStore";
import { eventService } from "../services/eventService";

export default function Events() {
  const navigate = useNavigate();
  const { events, activeEventId, setActiveEvent, fetchEvents, isLoadingEvents } = useEventStore();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  // Archive confirmation state
  const [archiveTarget, setArchiveTarget] = useState(null); // { id, name }
  const [isArchiving, setIsArchiving] = useState(false);

  // Status change state
  const [statusTarget, setStatusTarget] = useState(null); // { id, name, currentStatus }
  const [newStatus, setNewStatus] = useState("");
  const [isChangingStatus, setIsChangingStatus] = useState(false);

  const computeStatusFromTimings = (startStr, endStr) => {
    if (!startStr || !endStr) return "ACTIVE";
    const now = new Date();
    const start = new Date(startStr);
    const end = new Date(endStr);
    if (now >= start && now <= end) return "ACTIVE";
    if (now > end) return "COMPLETED";
    return "SCHEDULED";
  };

  const initialStart = new Date().toISOString().slice(0, 16);
  const initialEnd = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 16);

  const [formData, setFormData] = useState({
    name: "",
    code: "",
    year: new Date().getFullYear(),
    start_date: initialStart,
    end_date: initialEnd,
    status: computeStatusFromTimings(initialStart, initialEnd),
    location: "",
    city: "Hyderabad",
    state: "Telangana",
    country: "India",
    description: "",
  });

  const handleStartDateChange = (val) => {
    const computed = computeStatusFromTimings(val, formData.end_date);
    setFormData((prev) => ({
      ...prev,
      start_date: val,
      status: prev.status === "DRAFT" || prev.status === "PAUSED" ? prev.status : computed,
    }));
  };

  const handleEndDateChange = (val) => {
    const computed = computeStatusFromTimings(formData.start_date, val);
    setFormData((prev) => ({
      ...prev,
      end_date: val,
      status: prev.status === "DRAFT" || prev.status === "PAUSED" ? prev.status : computed,
    }));
  };

  const openCreateModal = () => {
    const s = new Date().toISOString().slice(0, 16);
    const e = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 16);
    setFormData({
      name: "",
      code: "",
      year: new Date().getFullYear(),
      start_date: s,
      end_date: e,
      status: computeStatusFromTimings(s, e),
      location: "",
      city: "Hyderabad",
      state: "Telangana",
      country: "India",
      description: "",
    });
    setFormError("");
    setShowCreateModal(true);
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setFormError("");

    const trimmedCode = (formData.code || "").trim().toUpperCase();
    if (!trimmedCode) {
      setFormError("Event Code is required.");
      return;
    }

    const duplicate = events.find(
      (ev) => ev.code?.toUpperCase() === trimmedCode
    );
    if (duplicate) {
      setFormError(
        `Event Code '${trimmedCode}' is already used by '${duplicate.name}'. Each event must have a unique code (e.g. ${trimmedCode}-2 or ${trimmedCode}-2026).`
      );
      return;
    }

    setIsSubmitting(true);
    try {
      await eventService.createEvent({
        ...formData,
        code: trimmedCode,
        year: parseInt(formData.year),
        start_date: new Date(formData.start_date).toISOString(),
        end_date: new Date(formData.end_date).toISOString(),
      });
      setShowCreateModal(false);
      await fetchEvents();
    } catch (err) {
      const detail = err.response?.data?.detail;
      let msg = "Failed to create event";
      if (typeof detail === "string") {
        msg = detail;
      } else if (detail && typeof detail === "object") {
        msg =
          detail.message ||
          (Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
            : JSON.stringify(detail));
      } else if (err.response?.data?.message) {
        msg = err.response.data.message;
      } else if (err.message) {
        msg = err.message;
      }
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleArchive = async () => {
    if (!archiveTarget) return;
    setIsArchiving(true);
    try {
      await eventService.archiveEvent(archiveTarget.id);
      setArchiveTarget(null);
      await fetchEvents();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (detail?.message || err.response?.data?.message || err.message || "Failed to archive event");
      alert("Failed to archive: " + msg);
    } finally {
      setIsArchiving(false);
    }
  };

  const handleChangeStatus = async () => {
    if (!statusTarget || !newStatus) return;
    setIsChangingStatus(true);
    try {
      await eventService.updateEvent(statusTarget.id, { status: newStatus });
      setStatusTarget(null);
      setNewStatus("");
      await fetchEvents();
    } catch (err) {
      alert("Failed to update status: " + (err.response?.data?.detail?.message || err.message));
    } finally {
      setIsChangingStatus(false);
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case "LIVE":
      case "ACTIVE":
        return "badge bg-success";
      case "SCHEDULED":
        return "badge bg-primary";
      case "PAUSED":
        return "badge bg-warning text-dark";
      case "COMPLETED":
        return "badge bg-secondary";
      case "ARCHIVED":
        return "badge bg-dark";
      default:
        return "badge bg-info";
    }
  };

  return (
    <div className="cc-page" style={{ padding: "24px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--cc-text-primary)" }}>
            <i className="bi bi-calendar-event-fill me-2" style={{ color: "var(--cc-accent)" }} />
            Festival & Event Management
          </h2>
          <p style={{ margin: "4px 0 0", color: "var(--cc-text-muted)", fontSize: 13 }}>
            Multi-Event command center with strict data isolation, role-based boundaries, and site operations.
          </p>
        </div>
        <button
          className="btn btn-primary btn-sm d-flex align-items-center gap-2"
          onClick={openCreateModal}
          style={{ padding: "8px 16px", fontWeight: 600 }}
        >
          <i className="bi bi-plus-lg" />
          Create New Event
        </button>
      </div>

      {/* Events Grid */}
      {isLoadingEvents && events.length === 0 ? (
        <div className="text-center py-5" style={{ color: "var(--cc-text-muted)" }}>
          <div className="spinner-border text-primary mb-2" role="status" />
          <div>Loading accessible events...</div>
        </div>
      ) : events.length === 0 ? (
        <div className="card p-5 text-center" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
          <i className="bi bi-calendar-x mb-3" style={{ fontSize: 48, color: "var(--cc-text-muted)" }} />
          <h5>No Events Found</h5>
          <p style={{ color: "var(--cc-text-muted)", fontSize: 13 }}>
            You haven't been assigned to any events yet or no events exist.
          </p>
        </div>
      ) : (
        <div className="row g-4">
          {events.map((evt) => {
            const isCurrent = evt.id === activeEventId;
            return (
              <div key={evt.id} className="col-12 col-lg-6 col-xl-4">
                <div
                  className="card h-100"
                  style={{
                    background: "var(--cc-card-bg)",
                    border: isCurrent ? "2px solid var(--cc-accent)" : "1px solid var(--cc-border)",
                    boxShadow: isCurrent ? "0 0 16px rgba(45, 126, 247, 0.25)" : "none",
                    borderRadius: 12,
                    position: "relative",
                    overflow: "hidden",
                  }}
                >
                  {isCurrent && (
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        background: "var(--cc-accent)",
                        color: "#fff",
                        fontSize: 10,
                        fontWeight: 700,
                        padding: "4px 12px",
                        borderBottomLeftRadius: 8,
                        letterSpacing: 0.5,
                      }}
                    >
                      ACTIVE CONTEXT
                    </div>
                  )}

                  <div className="card-body p-4 d-flex flex-column">
                    <div className="d-flex justify-content-between align-items-start mb-2">
                      <div>
                        <span className={getStatusBadgeClass(evt.status)} style={{ fontSize: 10, marginRight: 6 }}>
                          {evt.status}
                        </span>
                        <span className="badge bg-dark border" style={{ fontSize: 10, borderColor: "var(--cc-border)" }}>
                          {evt.code}
                        </span>
                      </div>
                    </div>

                    <h5 style={{ fontWeight: 700, color: "var(--cc-text-primary)", margin: "8px 0 4px" }}>
                      {evt.name}
                    </h5>

                    <p style={{ fontSize: 12, color: "var(--cc-text-muted)", flexGrow: 1, minHeight: 36 }}>
                      {evt.description || "No description provided."}
                    </p>

                    <div style={{ fontSize: 12, color: "var(--cc-text-muted)", marginBottom: 16 }}>
                      <div className="d-flex align-items-center gap-2 mb-1">
                        <i className="bi bi-geo-alt text-primary" />
                        <span>{evt.location ? `${evt.location}, ${evt.city}` : evt.city || "India"}</span>
                      </div>
                      <div className="d-flex align-items-center gap-2">
                        <i className="bi bi-calendar3 text-primary" />
                        <span>
                          {new Date(evt.start_date).toLocaleDateString()} — {new Date(evt.end_date).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    {/* Operational Metrics */}
                    <div
                      className="p-3 mb-3"
                      style={{
                        background: "var(--cc-bg-secondary, rgba(255,255,255,0.03))",
                        borderRadius: 8,
                        border: "1px solid var(--cc-border)",
                      }}
                    >
                      <div className="row text-center g-2">
                        <div className="col-4">
                          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                            {evt.site_count || 0}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Sites</div>
                        </div>
                        <div className="col-4">
                          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                            {evt.camera_count || 0}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Cameras</div>
                        </div>
                        <div className="col-4">
                          <div style={{ fontSize: 18, fontWeight: 700, color: evt.active_alert_count > 0 ? "var(--cc-red)" : "var(--cc-text-primary)" }}>
                            {evt.active_alert_count || 0}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Alerts</div>
                        </div>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="d-flex gap-2 mt-auto flex-wrap">
                      {!isCurrent ? (
                        <button
                          className="btn btn-outline-primary btn-sm flex-grow-1"
                          onClick={() => {
                            setActiveEvent(evt);
                            navigate("/dashboard");
                          }}
                          title="Select this event and switch dashboard context"
                        >
                          <i className="bi bi-check2-circle me-1" />
                          Select Event
                        </button>
                      ) : (
                        <button
                          className="btn btn-success btn-sm flex-grow-1"
                          onClick={() => navigate("/dashboard")}
                          title="Click to view Command Center Dashboard"
                        >
                          <i className="bi bi-broadcast me-1" />
                          Active Context (View Dashboard)
                        </button>
                      )}
                      <Link
                        to={`/sites?event_id=${evt.id}`}
                        className="btn btn-outline-secondary btn-sm"
                        title="Manage Sites"
                      >
                        <i className="bi bi-geo-alt" />
                      </Link>
                      <Link
                        to={`/events/${evt.id}/access`}
                        className="btn btn-outline-secondary btn-sm"
                        title="User Access"
                      >
                        <i className="bi bi-people" />
                      </Link>
                      {/* Change Status button — only show if not ARCHIVED */}
                      {evt.status !== "ARCHIVED" && (
                        <button
                          className="btn btn-outline-warning btn-sm"
                          title="Change Status"
                          onClick={() => {
                            setStatusTarget({ id: evt.id, name: evt.name, currentStatus: evt.status });
                            setNewStatus(evt.status);
                          }}
                        >
                          <i className="bi bi-arrow-repeat" />
                        </button>
                      )}
                      {/* Archive button — only show if not already ARCHIVED */}
                      {evt.status !== "ARCHIVED" && (
                        <button
                          className="btn btn-outline-danger btn-sm"
                          title="Archive / Stop Event"
                          onClick={() => setArchiveTarget({ id: evt.id, name: evt.name })}
                        >
                          <i className="bi bi-archive" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Event Modal */}
      {showCreateModal && (
        <div
          className="modal show d-block"
          style={{ background: "rgba(0,0,0,0.7)", zIndex: 1050 }}
          tabIndex="-1"
        >
          <div className="modal-dialog modal-dialog-centered modal-lg">
            <div className="modal-content" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
              <div className="modal-header" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title text-white">Create New Event / Festival</h5>
                <button
                  type="button"
                  className="btn-close btn-close-white"
                  onClick={() => setShowCreateModal(false)}
                />
              </div>
              <form onSubmit={handleCreate}>
                <div className="modal-body p-4">
                  {formError && (
                    <div className="alert alert-danger p-2 mb-3" style={{ fontSize: 13 }}>
                      {formError}
                    </div>
                  )}

                  <div className="row g-3">
                    <div className="col-md-7">
                      <label className="form-label text-muted small">Event Name</label>
                      <input
                        type="text"
                        className="form-control"
                        required
                        placeholder="e.g. Hyderabad Vijayadashami 2026"
                        value={formData.name}
                        onChange={(e) => {
                          const val = e.target.value;
                          setFormData((prev) => {
                            const cleanCode = val
                              .trim()
                              .toUpperCase()
                              .replace(/[^A-Z0-9\s-]/g, "")
                              .replace(/\s+/g, "-")
                              .slice(0, 16);
                            return {
                              ...prev,
                              name: val,
                              ...(!prev.codeEdited && cleanCode ? { code: cleanCode } : {}),
                            };
                          });
                        }}
                      />
                    </div>
                    <div className="col-md-5">
                      <label className="form-label text-muted small">Event Code (Unique)</label>
                      <input
                        type="text"
                        className={`form-control ${events.some((ev) => ev.code?.toUpperCase() === (formData.code || "").trim().toUpperCase()) ? "is-invalid" : ""}`}
                        required
                        placeholder="e.g. HYD-VIJ-2026"
                        value={formData.code}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            code: e.target.value.toUpperCase().replace(/\s+/g, "-"),
                            codeEdited: true,
                          })
                        }
                      />
                      {events.some((ev) => ev.code?.toUpperCase() === (formData.code || "").trim().toUpperCase()) && (
                        <div className="invalid-feedback d-block mt-1" style={{ fontSize: 11 }}>
                          <i className="bi bi-exclamation-triangle-fill me-1" />
                          Code &apos;{(formData.code || "").trim().toUpperCase()}&apos; is already in use! Please choose a unique code (e.g. {(formData.code || "").trim().toUpperCase()}-2026).
                        </div>
                      )}
                    </div>

                    <div className="col-md-4">
                      <label className="form-label text-muted small">Year</label>
                      <input
                        type="number"
                        className="form-control"
                        required
                        value={formData.year}
                        onChange={(e) => setFormData({ ...formData, year: e.target.value })}
                      />
                    </div>
                    <div className="col-md-4">
                      <label className="form-label text-muted small">Start Date</label>
                      <input
                        type="datetime-local"
                        className="form-control"
                        required
                        value={formData.start_date}
                        onChange={(e) => handleStartDateChange(e.target.value)}
                      />
                    </div>
                    <div className="col-md-4">
                      <label className="form-label text-muted small">End Date</label>
                      <input
                        type="datetime-local"
                        className="form-control"
                        required
                        value={formData.end_date}
                        onChange={(e) => handleEndDateChange(e.target.value)}
                      />
                    </div>

                    <div className="col-md-6">
                      <label className="form-label text-muted small">Location Name</label>
                      <input
                        type="text"
                        className="form-control"
                        placeholder="e.g. NTR Grounds, Tank Bund"
                        value={formData.location}
                        onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                      />
                    </div>
                    <div className="col-md-3">
                      <label className="form-label text-muted small">City</label>
                      <input
                        type="text"
                        className="form-control"
                        value={formData.city}
                        onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                      />
                    </div>
                    <div className="col-md-3">
                      <label className="form-label text-muted small d-flex justify-content-between align-items-center">
                        <span>Status</span>
                        {formData.status === "ACTIVE" && (
                          <span className="text-success fw-semibold" style={{ fontSize: 10 }}>
                            <i className="bi bi-broadcast me-1" />Live Now
                          </span>
                        )}
                        {formData.status === "SCHEDULED" && (
                          <span className="text-primary fw-semibold" style={{ fontSize: 10 }}>
                            <i className="bi bi-clock me-1" />Upcoming
                          </span>
                        )}
                        {formData.status === "COMPLETED" && (
                          <span className="text-secondary fw-semibold" style={{ fontSize: 10 }}>
                            <i className="bi bi-check-circle me-1" />Past
                          </span>
                        )}
                      </label>
                      <select
                        className="form-select"
                        value={formData.status}
                        onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                      >
                        <option value="ACTIVE">ACTIVE / LIVE (Current Window)</option>
                        <option value="SCHEDULED">SCHEDULED (Upcoming Window)</option>
                        <option value="COMPLETED">COMPLETED (Concluded)</option>
                        <option value="DRAFT">DRAFT (Manual Planning)</option>
                        <option value="PAUSED">PAUSED (Manual Hold)</option>
                      </select>
                    </div>

                    <div className="col-12">
                      <label className="form-label text-muted small">Description</label>
                      <textarea
                        className="form-control"
                        rows="2"
                        placeholder="Operational scope, anticipated crowds, security protocols..."
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      />
                    </div>
                  </div>
                </div>
                <div className="modal-footer" style={{ borderColor: "var(--cc-border)" }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setShowCreateModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary btn-sm"
                    disabled={isSubmitting || events.some((ev) => ev.code?.toUpperCase() === (formData.code || "").trim().toUpperCase())}
                  >
                    {isSubmitting ? "Creating..." : "Create Event"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── Archive Confirmation Modal ── */}
      {archiveTarget && (
        <div
          className="modal show d-block"
          style={{ background: "rgba(0,0,0,0.75)", zIndex: 1060 }}
          tabIndex="-1"
        >
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
              <div className="modal-header" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title text-warning">
                  <i className="bi bi-archive me-2" />
                  Archive Event?
                </h5>
                <button
                  type="button"
                  className="btn-close btn-close-white"
                  onClick={() => setArchiveTarget(null)}
                />
              </div>
              <div className="modal-body">
                <p style={{ color: "var(--cc-text-primary)" }}>
                  You are about to archive <strong>{archiveTarget.name}</strong>.
                </p>
                <ul style={{ color: "var(--cc-text-muted)", fontSize: 13 }}>
                  <li>Status will change to <strong>ARCHIVED</strong></li>
                  <li>The event will no longer appear as active</li>
                  <li>All historical data is preserved — nothing is deleted</li>
                  <li>Camera processing stops when workers are restarted</li>
                </ul>
              </div>
              <div className="modal-footer" style={{ borderColor: "var(--cc-border)" }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setArchiveTarget(null)}
                  disabled={isArchiving}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={handleArchive}
                  disabled={isArchiving}
                >
                  {isArchiving ? "Archiving..." : "Archive Event"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Change Status Modal ── */}
      {statusTarget && (
        <div
          className="modal show d-block"
          style={{ background: "rgba(0,0,0,0.75)", zIndex: 1060 }}
          tabIndex="-1"
        >
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
              <div className="modal-header" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title text-white">
                  <i className="bi bi-arrow-repeat me-2" />
                  Change Event Status
                </h5>
                <button
                  type="button"
                  className="btn-close btn-close-white"
                  onClick={() => setStatusTarget(null)}
                />
              </div>
              <div className="modal-body">
                <p style={{ color: "var(--cc-text-muted)", fontSize: 13, marginBottom: 12 }}>
                  Event: <strong style={{ color: "var(--cc-text-primary)" }}>{statusTarget.name}</strong>
                  &nbsp;|&nbsp;Current: <strong style={{ color: "var(--cc-text-primary)" }}>{statusTarget.currentStatus}</strong>
                </p>
                <label className="form-label text-muted small">New Status</label>
                <select
                  className="form-select"
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value)}
                >
                  <option value="DRAFT">DRAFT — Being planned, not live</option>
                  <option value="SCHEDULED">SCHEDULED — Upcoming, not started</option>
                  <option value="ACTIVE">ACTIVE / LIVE — Currently running</option>
                  <option value="PAUSED">PAUSED — Temporarily suspended</option>
                  <option value="COMPLETED">COMPLETED — Event finished</option>
                </select>
                <p style={{ fontSize: 11, color: "var(--cc-text-muted)", marginTop: 8 }}>
                  Note: To permanently archive use the Archive button. Status changes here are reversible.
                </p>
              </div>
              <div className="modal-footer" style={{ borderColor: "var(--cc-border)" }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setStatusTarget(null)}
                  disabled={isChangingStatus}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-warning btn-sm"
                  onClick={handleChangeStatus}
                  disabled={isChangingStatus || newStatus === statusTarget.currentStatus}
                >
                  {isChangingStatus ? "Saving..." : "Update Status"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}