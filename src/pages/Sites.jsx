import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useEventStore } from "../store/useEventStore";
import { eventService } from "../services/eventService";

export default function Sites() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { events, activeEventId, sites, fetchSites, activeSiteId, setActiveSiteId, isLoadingSites } = useEventStore();

  const selectedEventId = searchParams.get("event_id") || activeEventId;
  const currentEvent = events.find((e) => e.id === selectedEventId);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const [formData, setFormData] = useState({
    site_code: "",
    site_name: "",
    description: "",
    location: "",
    latitude: 17.4175,
    longitude: 78.4635,
    status: "ACTIVE",
  });

  useEffect(() => {
    if (selectedEventId) {
      fetchSites(selectedEventId);
    }
  }, [selectedEventId]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setFormError("");
    setIsSubmitting(true);
    try {
      await eventService.createSite({
        ...formData,
        event_id: selectedEventId,
        latitude: parseFloat(formData.latitude) || null,
        longitude: parseFloat(formData.longitude) || null,
      });
      setShowCreateModal(false);
      await fetchSites(selectedEventId);
    } catch (err) {
      setFormError(err.response?.data?.detail?.message || err.message || "Failed to create site");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (siteId, siteName) => {
    if (!window.confirm(`Are you sure you want to delete site "${siteName}"? Cameras assigned to this site will become unassigned.`)) {
      return;
    }
    try {
      await eventService.deleteSite(siteId);
      await fetchSites(selectedEventId);
    } catch (err) {
      alert("Failed to delete site: " + err.message);
    }
  };

  return (
    <div className="cc-page" style={{ padding: "24px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
        <div>
          <div className="d-flex align-items-center gap-2 mb-1">
            <Link to="/events" className="btn btn-outline-secondary btn-sm" style={{ padding: "2px 8px" }}>
              <i className="bi bi-arrow-left me-1" />
              Events
            </Link>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--cc-text-primary)" }}>
              <i className="bi bi-geo-alt-fill me-2" style={{ color: "var(--cc-accent)" }} />
              Physical Sites & Locations
            </h2>
          </div>
          <p style={{ margin: "4px 0 0", color: "var(--cc-text-muted)", fontSize: 13 }}>
            Operational sectors, entry/exit gates, and surveillance zones for{" "}
            <strong style={{ color: "var(--cc-text-primary)" }}>{currentEvent?.name || "Selected Event"}</strong>.
          </p>
        </div>

        <div className="d-flex align-items-center gap-3">
          {/* Event Switcher */}
          <select
            className="form-select form-select-sm"
            style={{ width: 240, background: "var(--cc-card-bg)", color: "var(--cc-text-primary)", borderColor: "var(--cc-border)" }}
            value={selectedEventId || ""}
            onChange={(e) => setSearchParams({ event_id: e.target.value })}
          >
            {events.map((evt) => (
              <option key={evt.id} value={evt.id}>
                {evt.name} ({evt.code})
              </option>
            ))}
          </select>

          <button
            className="btn btn-primary btn-sm d-flex align-items-center gap-2"
            onClick={() => setShowCreateModal(true)}
            style={{ padding: "8px 16px", fontWeight: 600 }}
          >
            <i className="bi bi-plus-lg" />
            Add Site
          </button>
        </div>
      </div>

      {/* Sites Grid */}
      {isLoadingSites && sites.length === 0 ? (
        <div className="text-center py-5" style={{ color: "var(--cc-text-muted)" }}>
          <div className="spinner-border text-primary mb-2" role="status" />
          <div>Loading operational sites...</div>
        </div>
      ) : sites.length === 0 ? (
        <div className="card p-5 text-center" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
          <i className="bi bi-geo mb-3" style={{ fontSize: 48, color: "var(--cc-text-muted)" }} />
          <h5>No Sites Configured</h5>
          <p style={{ color: "var(--cc-text-muted)", fontSize: 13 }}>
            Create operational sectors (e.g. North Gate Plaza, Main Sanctum, East Queue) to organize cameras.
          </p>
        </div>
      ) : (
        <div className="row g-4">
          {sites.map((site) => {
            const isSiteSelected = site.id === activeSiteId;
            return (
              <div key={site.id} className="col-12 col-md-6 col-xl-4">
                <div
                  className="card h-100"
                  style={{
                    background: "var(--cc-card-bg)",
                    border: isSiteSelected ? "2px solid var(--cc-accent)" : "1px solid var(--cc-border)",
                    borderRadius: 12,
                  }}
                >
                  <div className="card-body p-4 d-flex flex-column">
                    <div className="d-flex justify-content-between align-items-start mb-2">
                      <span className="badge bg-primary" style={{ fontSize: 10 }}>
                        {site.site_code}
                      </span>
                      <span className="badge bg-success" style={{ fontSize: 10 }}>
                        {site.status}
                      </span>
                    </div>

                    <h5 style={{ fontWeight: 700, color: "var(--cc-text-primary)", margin: "8px 0 4px" }}>
                      {site.site_name}
                    </h5>

                    <p style={{ fontSize: 12, color: "var(--cc-text-muted)", flexGrow: 1, minHeight: 36 }}>
                      {site.description || "No operational notes provided."}
                    </p>

                    <div style={{ fontSize: 12, color: "var(--cc-text-muted)", marginBottom: 16 }}>
                      <div className="d-flex align-items-center gap-2">
                        <i className="bi bi-geo text-primary" />
                        <span>{site.location || "Coordinates: " + site.latitude + ", " + site.longitude}</span>
                      </div>
                    </div>

                    {/* Camera Health at this Site */}
                    <div
                      className="p-3 mb-3 d-flex justify-content-between align-items-center"
                      style={{
                        background: "var(--cc-bg-secondary, rgba(255,255,255,0.03))",
                        borderRadius: 8,
                        border: "1px solid var(--cc-border)",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                          {site.camera_count || 0}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Total Cameras</div>
                      </div>
                      <div className="text-end">
                        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--cc-green)" }}>
                          {site.online_camera_count || 0}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Online Stream</div>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="d-flex gap-2 mt-auto">
                      <button
                        className={`btn btn-sm flex-grow-1 ${isSiteSelected ? "btn-primary" : "btn-outline-primary"}`}
                        onClick={() => setActiveSiteId(isSiteSelected ? null : site.id)}
                      >
                        <i className="bi bi-filter me-1" />
                        {isSiteSelected ? "Filtered (Clear)" : "Filter Command Center"}
                      </button>
                      <Link
                        to={`/cameras?site_id=${site.id}`}
                        className="btn btn-outline-secondary btn-sm"
                        title="View Site Cameras"
                      >
                        <i className="bi bi-camera-video" />
                      </Link>
                      <button
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => handleDelete(site.id, site.site_name)}
                        title="Delete Site"
                      >
                        <i className="bi bi-trash" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Site Modal */}
      {showCreateModal && (
        <div
          className="modal show d-block"
          style={{ background: "rgba(0,0,0,0.7)", zIndex: 1050 }}
          tabIndex="-1"
        >
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
              <div className="modal-header" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title text-white">Add Operational Site</h5>
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
                    <div className="col-8">
                      <label className="form-label text-muted small">Site Name</label>
                      <input
                        type="text"
                        className="form-control"
                        required
                        placeholder="e.g. VIP Holding Area"
                        value={formData.site_name}
                        onChange={(e) => setFormData({ ...formData, site_name: e.target.value })}
                      />
                    </div>
                    <div className="col-4">
                      <label className="form-label text-muted small">Site Code</label>
                      <input
                        type="text"
                        className="form-control"
                        required
                        placeholder="e.g. SITE-VIP"
                        value={formData.site_code}
                        onChange={(e) => setFormData({ ...formData, site_code: e.target.value.toUpperCase() })}
                      />
                    </div>

                    <div className="col-12">
                      <label className="form-label text-muted small">Physical Location / Landmark</label>
                      <input
                        type="text"
                        className="form-control"
                        placeholder="e.g. South West Corner near Gate 4"
                        value={formData.location}
                        onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                      />
                    </div>

                    <div className="col-6">
                      <label className="form-label text-muted small">Latitude</label>
                      <input
                        type="number"
                        step="any"
                        className="form-control"
                        value={formData.latitude}
                        onChange={(e) => setFormData({ ...formData, latitude: e.target.value })}
                      />
                    </div>
                    <div className="col-6">
                      <label className="form-label text-muted small">Longitude</label>
                      <input
                        type="number"
                        step="any"
                        className="form-control"
                        value={formData.longitude}
                        onChange={(e) => setFormData({ ...formData, longitude: e.target.value })}
                      />
                    </div>

                    <div className="col-12">
                      <label className="form-label text-muted small">Description</label>
                      <textarea
                        className="form-control"
                        rows="2"
                        placeholder="Operational purpose, security constraints, access routes..."
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
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? "Creating..." : "Save Site"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}