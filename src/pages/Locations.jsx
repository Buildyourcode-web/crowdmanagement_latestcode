import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEventStore } from "../store/useEventStore";
import { locationService } from "../services/locationService";

const getApiErrorMessage = (err, fallback = "An error occurred") => {
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (typeof err.response?.data?.message === "string") return err.response.data.message;
  return err.message || fallback;
};

export default function Locations() {
  const navigate = useNavigate();
  const { events, activeEventId, setActiveEvent, activeLocationId, setActiveLocation, fetchEvents } = useEventStore();

  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Add Location Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [addStep, setAddStep] = useState(1); // 1: Info, 2: OTP
  const [addForm, setAddForm] = useState({
    name: "",
    code: "",
    city: "Hyderabad",
    state: "Telangana",
    email: "",
    access_code: "",
    confirm_access_code: "",
    verification_code: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [addError, setAddError] = useState("");
  const [otpCountdown, setOtpCountdown] = useState(0);

  // Access Verification & Festival Modal State
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [accessMode, setAccessMode] = useState("VERIFY"); // "VERIFY", "FORGOT_OTP", "FORGOT_RESET", "FESTIVALS"
  const [accessCodeInput, setAccessCodeInput] = useState("");
  const [accessError, setAccessError] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);

  // Forgot Code Recovery State
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [newAccessCode, setNewAccessCode] = useState("");
  const [confirmNewCode, setConfirmNewCode] = useState("");
  const [recoverySuccessMsg, setRecoverySuccessMsg] = useState("");

  // Festivals under verified Location State
  const [locationEvents, setLocationEvents] = useState([]);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [showAddFestForm, setShowAddFestForm] = useState(false);
  const [showLinkExisting, setShowLinkExisting] = useState(false);
  const [selectedExistingEventId, setSelectedExistingEventId] = useState("");

  const initialStart = new Date().toISOString().slice(0, 16);
  const initialEnd = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 16);

  const [festForm, setFestForm] = useState({
    name: "",
    code: "",
    year: new Date().getFullYear(),
    start_date: initialStart,
    end_date: initialEnd,
    status: "ACTIVE",
    description: "",
  });

  const loadLocations = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await locationService.getLocations();
      setLocations(data);
    } catch (err) {
      setError(err.response?.data?.detail?.message || err.message || "Failed to load locations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLocations();
    fetchEvents();
  }, []);

  // OTP Countdown timer
  useEffect(() => {
    if (otpCountdown > 0) {
      const timer = setTimeout(() => setOtpCountdown(otpCountdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [otpCountdown]);

  // Handle Add Location: Step 1 -> Send OTP
  const handleSendAddOtp = async (e) => {
    e.preventDefault();
    setAddError("");

    if (!addForm.name || !addForm.code || !addForm.email || !addForm.access_code) {
      setAddError("Please fill in all required fields.");
      return;
    }

    if (addForm.access_code.length < 4) {
      setAddError("Access code must be at least 4 characters.");
      return;
    }

    if (addForm.access_code !== addForm.confirm_access_code) {
      setAddError("Access codes do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await locationService.sendVerificationCode({
        email: addForm.email.trim(),
        location_name: addForm.name.trim(),
        location_code: addForm.code.trim().toUpperCase(),
        city: addForm.city.trim(),
        state: addForm.state.trim(),
        purpose: "CREATE_LOCATION",
      });
      setAddStep(2);
      setOtpCountdown(60);
    } catch (err) {
      setAddError(getApiErrorMessage(err, "Failed to send code"));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Add Location: Step 2 -> Create Location
  const handleCreateLocation = async (e) => {
    e.preventDefault();
    setAddError("");

    if (!addForm.verification_code || addForm.verification_code.length < 4) {
      setAddError("Please enter the verification code sent to your email.");
      return;
    }

    setIsSubmitting(true);
    try {
      await locationService.createLocation({
        name: addForm.name.trim(),
        code: addForm.code.trim().toUpperCase(),
        city: addForm.city.trim(),
        state: addForm.state.trim(),
        email: addForm.email.trim(),
        access_code: addForm.access_code,
        verification_code: addForm.verification_code.trim(),
      });
      setShowAddModal(false);
      setAddStep(1);
      setAddForm({
        name: "",
        code: "",
        city: "Hyderabad",
        state: "Telangana",
        email: "",
        access_code: "",
        confirm_access_code: "",
        verification_code: "",
      });
      await loadLocations();
    } catch (err) {
      setAddError(getApiErrorMessage(err, "Failed to create location"));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Location Modal
  const openLocationModal = (loc) => {
    setSelectedLocation(loc);
    setAccessMode("VERIFY");
    setAccessCodeInput("");
    setAccessError("");
    setRecoverySuccessMsg("");
    setRecoveryEmail(loc.email || "");
    setShowAddFestForm(false);
    setShowLinkExisting(false);
  };

  // Verify Location Access Code
  const handleVerifyAccessCode = async (e) => {
    e.preventDefault();
    setAccessError("");
    if (!accessCodeInput) {
      setAccessError("Please enter the location access code.");
      return;
    }

    setIsVerifying(true);
    try {
      await locationService.verifyAccessCode(selectedLocation.id, accessCodeInput);
      // Success -> transition to Festivals screen
      setAccessMode("FESTIVALS");
      loadLocationEvents(selectedLocation.id);
    } catch (err) {
      setAccessError(getApiErrorMessage(err, "Incorrect access code for this location. Access denied."));
    } finally {
      setIsVerifying(false);
    }
  };

  // Load Festivals for Location
  const loadLocationEvents = async (locId) => {
    setLoadingEvents(true);
    try {
      const data = await locationService.getLocationEvents(locId);
      setLocationEvents(data);
    } catch (err) {
      console.error("Failed to load location events:", err);
    } finally {
      setLoadingEvents(false);
    }
  };

  // Handle Forgot Access Code: Step 1 -> Send Recovery OTP
  const handleSendRecoveryOtp = async (e) => {
    e.preventDefault();
    setAccessError("");
    if (!recoveryEmail) {
      setAccessError("Please enter your registered email.");
      return;
    }

    setIsVerifying(true);
    try {
      await locationService.forgotAccessCode(selectedLocation.id, recoveryEmail.trim());
      setAccessMode("FORGOT_RESET");
      setOtpCountdown(60);
    } catch (err) {
      setAccessError(getApiErrorMessage(err, "Failed to send recovery code"));
    } finally {
      setIsVerifying(false);
    }
  };

  // Handle Forgot Access Code: Step 2 -> Reset Code
  const handleResetAccessCode = async (e) => {
    e.preventDefault();
    setAccessError("");

    if (!recoveryCode) {
      setAccessError("Please enter the verification code.");
      return;
    }
    if (!newAccessCode || newAccessCode.length < 4) {
      setAccessError("New access code must be at least 4 characters.");
      return;
    }
    if (newAccessCode !== confirmNewCode) {
      setAccessError("New access codes do not match.");
      return;
    }

    setIsVerifying(true);
    try {
      await locationService.resetAccessCode(selectedLocation.id, {
        email: recoveryEmail.trim(),
        verification_code: recoveryCode.trim(),
        new_access_code: newAccessCode,
      });
      setAccessMode("VERIFY");
      setAccessCodeInput("");
      setRecoverySuccessMsg("Access code reset successfully! Please enter your new access code to continue.");
    } catch (err) {
      setAccessError(getApiErrorMessage(err, "Failed to reset access code"));
    } finally {
      setIsVerifying(false);
    }
  };

  // Create new Festival under Location
  const handleCreateFestival = async (e) => {
    e.preventDefault();
    setAccessError("");

    if (!festForm.name || !festForm.code) {
      setAccessError("Festival name and code are required.");
      return;
    }

    setIsSubmitting(true);
    try {
      await locationService.createLocationEvent(selectedLocation.id, {
        ...festForm,
        code: festForm.code.trim().toUpperCase(),
        year: parseInt(festForm.year),
        start_date: new Date(festForm.start_date).toISOString(),
        end_date: new Date(festForm.end_date).toISOString(),
      });
      setShowAddFestForm(false);
      setFestForm({
        name: "",
        code: "",
        year: new Date().getFullYear(),
        start_date: initialStart,
        end_date: initialEnd,
        status: "ACTIVE",
        description: "",
      });
      await loadLocationEvents(selectedLocation.id);
      await loadLocations();
      await fetchEvents();
    } catch (err) {
      setAccessError(getApiErrorMessage(err, "Failed to add festival"));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Safeguard #1: Deliberately link existing event to location
  const handleLinkExistingEvent = async (e) => {
    e.preventDefault();
    if (!selectedExistingEventId) return;

    setIsSubmitting(true);
    try {
      await locationService.linkExistingEvent(selectedLocation.id, selectedExistingEventId);
      setShowLinkExisting(false);
      setSelectedExistingEventId("");
      await loadLocationEvents(selectedLocation.id);
      await loadLocations();
      await fetchEvents();
    } catch (err) {
      setAccessError(getApiErrorMessage(err, "Failed to link event"));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Festival in Dashboard
  const handleOpenDashboard = (event) => {
    setActiveLocation(selectedLocation);
    setActiveEvent(event);
    setSelectedLocation(null);
    navigate("/dashboard");
  };

  const getStatusBadge = (status) => {
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
      default:
        return "badge bg-info";
    }
  };

  return (
    <div className="cc-page" style={{ padding: "24px" }}>
      {/* Page Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--cc-text-primary)" }}>
            <i className="bi bi-geo-alt-fill me-2" style={{ color: "var(--cc-accent)" }} />
            Location Management
          </h2>
          <p style={{ margin: "4px 0 0", color: "var(--cc-text-muted)", fontSize: 13 }}>
            Select a location, verify access code, and launch into festival command center context.
          </p>
        </div>
        <button
          className="btn btn-primary btn-sm d-flex align-items-center gap-2"
          onClick={() => {
            setAddStep(1);
            setAddError("");
            setShowAddModal(true);
          }}
          style={{ padding: "8px 16px", fontWeight: 600 }}
        >
          <i className="bi bi-plus-lg" />
          Add Location
        </button>
      </div>

      {error && (
        <div className="alert alert-danger py-2 mb-4" role="alert" style={{ fontSize: 13 }}>
          <i className="bi bi-exclamation-triangle me-2" />
          {error}
        </div>
      )}

      {/* Locations Grid */}
      {loading ? (
        <div className="text-center py-5" style={{ color: "var(--cc-text-muted)" }}>
          <div className="spinner-border text-primary mb-2" role="status" />
          <div>Loading locations...</div>
        </div>
      ) : locations.length === 0 ? (
        <div className="card p-5 text-center" style={{ background: "var(--cc-card-bg)", borderColor: "var(--cc-border)" }}>
          <i className="bi bi-geo-alt mb-3" style={{ fontSize: 48, color: "var(--cc-text-muted)" }} />
          <h5>No Locations Found</h5>
          <p style={{ color: "var(--cc-text-muted)", fontSize: 13 }}>
            Click "+ Add Location" to register your first administrative location.
          </p>
        </div>
      ) : (
        <div className="row g-4">
          {locations.map((loc) => {
            const isCurrentLoc = Boolean(activeLocationId && String(loc.id).toLowerCase() === String(activeLocationId).toLowerCase());
            return (
              <div key={loc.id} className="col-12 col-lg-6 col-xl-4">
                <div
                  className="card h-100"
                  style={{
                    background: "var(--cc-card-bg)",
                    border: isCurrentLoc ? "2px solid var(--cc-accent)" : "1px solid var(--cc-border)",
                    boxShadow: isCurrentLoc ? "0 0 16px rgba(45, 126, 247, 0.25)" : "none",
                    borderRadius: 12,
                    position: "relative",
                    overflow: "hidden",
                  }}
                >
                  {isCurrentLoc && (
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
                      CURRENT LOCATION
                    </div>
                  )}

                  <div className="card-body p-4 d-flex flex-column">
                    <div className="d-flex justify-content-between align-items-start mb-2">
                      <div>
                        <span className="badge bg-success" style={{ fontSize: 10, marginRight: 6 }}>
                          {loc.status}
                        </span>
                        <span className="badge bg-dark border" style={{ fontSize: 10, borderColor: "var(--cc-border)" }}>
                          {loc.code}
                        </span>
                      </div>
                    </div>

                    <h5 style={{ fontWeight: 700, color: "var(--cc-text-primary)", margin: "8px 0 4px" }}>
                      {loc.name}
                    </h5>

                    <div style={{ fontSize: 12, color: "var(--cc-text-muted)", marginBottom: 12 }}>
                      <div className="d-flex align-items-center gap-2 mb-1">
                        <i className="bi bi-geo text-primary" />
                        <span>{loc.city}, {loc.state}</span>
                      </div>
                      <div className="d-flex align-items-center gap-2">
                        <i className="bi bi-envelope text-primary" />
                        <span>{loc.email}</span>
                      </div>
                    </div>

                    {/* Operational Summary Card */}
                    <div
                      className="p-3 mb-3"
                      style={{
                        background: "var(--cc-bg-secondary, rgba(255,255,255,0.03))",
                        borderRadius: 8,
                        border: "1px solid var(--cc-border)",
                      }}
                    >
                      <div className="row text-center g-2">
                        <div className="col-6">
                          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--cc-text-primary)" }}>
                            {loc.festival_count || 0}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Festivals / Events</div>
                        </div>
                        <div className="col-6">
                          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--cc-accent)" }}>
                            <i className="bi bi-shield-lock" />
                          </div>
                          <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>Access Code Protected</div>
                        </div>
                      </div>
                    </div>

                    {/* Open Action Button */}
                    <button
                      className="btn btn-primary btn-sm w-100 mt-auto d-flex align-items-center justify-content-center gap-2"
                      onClick={() => openLocationModal(loc)}
                      style={{ padding: "10px 16px", fontWeight: 600 }}
                    >
                      <i className="bi bi-box-arrow-in-right" />
                      Open Location
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ========================================================================= */}
      {/* ADD LOCATION MODAL */}
      {/* ========================================================================= */}
      {showAddModal && (
        <div
          className="modal show d-block"
          style={{ background: "rgba(0,0,0,0.75)", zIndex: 1050 }}
          tabIndex="-1"
        >
          <div className="modal-dialog modal-dialog-centered" style={{ maxWidth: 500 }}>
            <div
              className="modal-content border-0"
              style={{ background: "var(--cc-card-bg)", color: "var(--cc-text-primary)", borderRadius: 12 }}
            >
              <div className="modal-header border-bottom" style={{ borderColor: "var(--cc-border)" }}>
                <h5 className="modal-title" style={{ fontSize: 16, fontWeight: 700 }}>
                  <i className="bi bi-geo-alt-fill text-primary me-2" />
                  {addStep === 1 ? "Add New Location" : "Verify Registered Email"}
                </h5>
                <button
                  type="button"
                  className="btn-close btn-close-white"
                  onClick={() => setShowAddModal(false)}
                />
              </div>

              {addStep === 1 ? (
                <form onSubmit={handleSendAddOtp}>
                  <div className="modal-body p-4" style={{ fontSize: 13 }}>
                    {addError && (
                      <div className="alert alert-danger py-2 mb-3" style={{ fontSize: 12 }}>
                        {addError}
                      </div>
                    )}

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">Location Name *</label>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder="e.g. Khairatabad"
                        value={addForm.name}
                        onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                        required
                      />
                    </div>

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">Location Code *</label>
                      <input
                        type="text"
                        className="form-control form-control-sm text-uppercase"
                        placeholder="e.g. KHB-001"
                        value={addForm.code}
                        onChange={(e) => setAddForm({ ...addForm, code: e.target.value })}
                        required
                      />
                    </div>

                    <div className="row g-2 mb-3">
                      <div className="col-6">
                        <label className="form-label text-muted mb-1">City *</label>
                        <input
                          type="text"
                          className="form-control form-control-sm"
                          value={addForm.city}
                          onChange={(e) => setAddForm({ ...addForm, city: e.target.value })}
                          required
                        />
                      </div>
                      <div className="col-6">
                        <label className="form-label text-muted mb-1">State *</label>
                        <input
                          type="text"
                          className="form-control form-control-sm"
                          value={addForm.state}
                          onChange={(e) => setAddForm({ ...addForm, state: e.target.value })}
                          required
                        />
                      </div>
                    </div>

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">Registered Email *</label>
                      <input
                        type="email"
                        className="form-control form-control-sm"
                        placeholder="admin@example.com"
                        value={addForm.email}
                        onChange={(e) => setAddForm({ ...addForm, email: e.target.value })}
                        required
                      />
                      <div className="form-text" style={{ fontSize: 11 }}>
                        A verification code will be sent to this email to create the location.
                      </div>
                    </div>

                    <div className="row g-2 mb-2">
                      <div className="col-6">
                        <label className="form-label text-muted mb-1">Location Access Code *</label>
                        <input
                          type="password"
                          className="form-control form-control-sm"
                          placeholder="Min 4 characters"
                          value={addForm.access_code}
                          onChange={(e) => setAddForm({ ...addForm, access_code: e.target.value })}
                          required
                        />
                      </div>
                      <div className="col-6">
                        <label className="form-label text-muted mb-1">Confirm Access Code *</label>
                        <input
                          type="password"
                          className="form-control form-control-sm"
                          placeholder="Repeat code"
                          value={addForm.confirm_access_code}
                          onChange={(e) => setAddForm({ ...addForm, confirm_access_code: e.target.value })}
                          required
                        />
                      </div>
                    </div>
                  </div>

                  <div className="modal-footer border-top" style={{ borderColor: "var(--cc-border)" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setShowAddModal(false)}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm d-flex align-items-center gap-2"
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? (
                        <>
                          <span className="spinner-border spinner-border-sm" role="status" />
                          Sending Code...
                        </>
                      ) : (
                        <>
                          <i className="bi bi-envelope-paper" />
                          Send Verification Code
                        </>
                      )}
                    </button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handleCreateLocation}>
                  <div className="modal-body p-4" style={{ fontSize: 13 }}>
                    {addError && (
                      <div className="alert alert-danger py-2 mb-3" style={{ fontSize: 12 }}>
                        {addError}
                      </div>
                    )}

                    <div
                      className="p-3 mb-3"
                      style={{
                        background: "rgba(45, 126, 247, 0.08)",
                        border: "1px solid rgba(45, 126, 247, 0.2)",
                        borderRadius: 8,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>
                        Verification Code Sent
                      </div>
                      <div style={{ color: "var(--cc-text-muted)", fontSize: 12, marginTop: 4 }}>
                        A single-use 6-digit code was sent to <strong>{addForm.email}</strong> for Location: <strong>{addForm.name}</strong>.
                      </div>
                    </div>

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">Enter 6-Digit Verification Code *</label>
                      <input
                        type="text"
                        maxLength="10"
                        className="form-control text-center font-monospace"
                        style={{ fontSize: 20, letterSpacing: 4 }}
                        placeholder="482913"
                        value={addForm.verification_code}
                        onChange={(e) => setAddForm({ ...addForm, verification_code: e.target.value })}
                        required
                        autoFocus
                      />
                    </div>

                    <div className="d-flex justify-content-between align-items-center">
                      <span style={{ fontSize: 12, color: "var(--cc-text-muted)" }}>
                        {otpCountdown > 0 ? `Resend available in ${otpCountdown}s` : ""}
                      </span>
                      {otpCountdown === 0 && (
                        <button
                          type="button"
                          className="btn btn-link btn-sm p-0 text-decoration-none"
                          style={{ fontSize: 12 }}
                          onClick={handleSendAddOtp}
                        >
                          Resend Code
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="modal-footer border-top" style={{ borderColor: "var(--cc-border)" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setAddStep(1)}
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      className="btn btn-success btn-sm d-flex align-items-center gap-2"
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? (
                        <>
                          <span className="spinner-border spinner-border-sm" role="status" />
                          Creating...
                        </>
                      ) : (
                        <>
                          <i className="bi bi-check-lg" />
                          Create Location
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* ACCESS CODE & FESTIVAL SELECTION MODAL */}
      {/* ========================================================================= */}
      {selectedLocation && (
        <div
          className="modal show d-block"
          style={{ background: "rgba(0,0,0,0.8)", zIndex: 1050 }}
          tabIndex="-1"
        >
          <div className="modal-dialog modal-dialog-centered" style={{ maxWidth: accessMode === "FESTIVALS" ? 700 : 450 }}>
            <div
              className="modal-content border-0"
              style={{ background: "var(--cc-card-bg)", color: "var(--cc-text-primary)", borderRadius: 12 }}
            >
              {/* Header */}
              <div className="modal-header border-bottom" style={{ borderColor: "var(--cc-border)" }}>
                <div>
                  <h5 className="modal-title mb-0" style={{ fontSize: 16, fontWeight: 700 }}>
                    {selectedLocation.name}
                  </h5>
                  <span className="badge bg-dark border mt-1" style={{ fontSize: 10, borderColor: "var(--cc-border)" }}>
                    Location Code: {selectedLocation.code}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn-close btn-close-white"
                  onClick={() => setSelectedLocation(null)}
                />
              </div>

              {/* Mode 1: Access Code Verification */}
              {accessMode === "VERIFY" && (
                <form onSubmit={handleVerifyAccessCode}>
                  <div className="modal-body p-4" style={{ fontSize: 13 }}>
                    {recoverySuccessMsg && (
                      <div className="alert alert-success py-2 mb-3" style={{ fontSize: 12 }}>
                        {recoverySuccessMsg}
                      </div>
                    )}
                    {accessError && (
                      <div className="alert alert-danger py-2 mb-3" style={{ fontSize: 12 }}>
                        {accessError}
                      </div>
                    )}

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">Access Code *</label>
                      <input
                        type="password"
                        className="form-control"
                        placeholder="Enter location access code"
                        value={accessCodeInput}
                        onChange={(e) => setAccessCodeInput(e.target.value)}
                        autoFocus
                        required
                      />
                    </div>

                    <div className="d-flex justify-content-between align-items-center">
                      <button
                        type="button"
                        className="btn btn-link btn-sm p-0 text-decoration-none"
                        style={{ fontSize: 12, color: "var(--cc-accent)" }}
                        onClick={() => {
                          setAccessMode("FORGOT_OTP");
                          setAccessError("");
                          setRecoveryEmail(selectedLocation.email || "");
                        }}
                      >
                        Forgot Access Code?
                      </button>
                    </div>
                  </div>

                  <div className="modal-footer border-top" style={{ borderColor: "var(--cc-border)" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setSelectedLocation(null)}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm d-flex align-items-center gap-2"
                      disabled={isVerifying}
                    >
                      {isVerifying ? (
                        <>
                          <span className="spinner-border spinner-border-sm" role="status" />
                          Verifying...
                        </>
                      ) : (
                        <>
                          <i className="bi bi-arrow-right" />
                          Continue
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* Mode 2a: Forgot Access Code (Request OTP) */}
              {accessMode === "FORGOT_OTP" && (
                <form onSubmit={handleSendRecoveryOtp}>
                  <div className="modal-body p-4" style={{ fontSize: 13 }}>
                    {accessError && (
                      <div className="alert alert-danger py-2 mb-3" style={{ fontSize: 12 }}>
                        {accessError}
                      </div>
                    )}

                    <p style={{ color: "var(--cc-text-muted)", fontSize: 12, marginBottom: 16 }}>
                      Enter the registered email for <strong>{selectedLocation.name}</strong>. A recovery verification code will be sent to reset your access code.
                    </p>

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">Registered Email *</label>
                      <input
                        type="email"
                        className="form-control form-control-sm"
                        value={recoveryEmail}
                        onChange={(e) => setRecoveryEmail(e.target.value)}
                        required
                        autoFocus
                      />
                    </div>
                  </div>

                  <div className="modal-footer border-top" style={{ borderColor: "var(--cc-border)" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setAccessMode("VERIFY")}
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm d-flex align-items-center gap-2"
                      disabled={isVerifying}
                    >
                      {isVerifying ? (
                        <>
                          <span className="spinner-border spinner-border-sm" role="status" />
                          Sending Code...
                        </>
                      ) : (
                        <>
                          <i className="bi bi-envelope-paper" />
                          Send Recovery Code
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* Mode 2b: Forgot Access Code (Enter OTP & Set New Password) */}
              {accessMode === "FORGOT_RESET" && (
                <form onSubmit={handleResetAccessCode}>
                  <div className="modal-body p-4" style={{ fontSize: 13 }}>
                    {accessError && (
                      <div className="alert alert-danger py-2 mb-3" style={{ fontSize: 12 }}>
                        {accessError}
                      </div>
                    )}

                    <div
                      className="p-3 mb-3"
                      style={{
                        background: "rgba(45, 126, 247, 0.08)",
                        border: "1px solid rgba(45, 126, 247, 0.2)",
                        borderRadius: 8,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: "var(--cc-text-primary)" }}>
                        Recovery Code Sent
                      </div>
                      <div style={{ color: "var(--cc-text-muted)", fontSize: 12, marginTop: 4 }}>
                        A verification code was sent to <strong>{recoveryEmail}</strong>.
                      </div>
                    </div>

                    <div className="mb-3">
                      <label className="form-label text-muted mb-1">6-Digit Verification Code *</label>
                      <input
                        type="text"
                        maxLength="10"
                        className="form-control text-center font-monospace"
                        style={{ fontSize: 18, letterSpacing: 3 }}
                        placeholder="482913"
                        value={recoveryCode}
                        onChange={(e) => setRecoveryCode(e.target.value)}
                        required
                        autoFocus
                      />
                    </div>

                    <div className="row g-2 mb-2">
                      <div className="col-6">
                        <label className="form-label text-muted mb-1">New Access Code *</label>
                        <input
                          type="password"
                          className="form-control form-control-sm"
                          placeholder="Min 4 chars"
                          value={newAccessCode}
                          onChange={(e) => setNewAccessCode(e.target.value)}
                          required
                        />
                      </div>
                      <div className="col-6">
                        <label className="form-label text-muted mb-1">Confirm New Code *</label>
                        <input
                          type="password"
                          className="form-control form-control-sm"
                          placeholder="Repeat code"
                          value={confirmNewCode}
                          onChange={(e) => setConfirmNewCode(e.target.value)}
                          required
                        />
                      </div>
                    </div>
                  </div>

                  <div className="modal-footer border-top" style={{ borderColor: "var(--cc-border)" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setAccessMode("FORGOT_OTP")}
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      className="btn btn-success btn-sm d-flex align-items-center gap-2"
                      disabled={isVerifying}
                    >
                      {isVerifying ? (
                        <>
                          <span className="spinner-border spinner-border-sm" role="status" />
                          Updating...
                        </>
                      ) : (
                        <>
                          <i className="bi bi-shield-check" />
                          Set New Access Code
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* Mode 3: Festivals & Events for Verified Location */}
              {accessMode === "FESTIVALS" && (
                <div className="modal-body p-4" style={{ fontSize: 13 }}>
                  <div className="d-flex justify-content-between align-items-center mb-3">
                    <span style={{ fontWeight: 600, color: "var(--cc-text-muted)" }}>
                      Available Festivals & Events
                    </span>
                    <div className="d-flex gap-2">
                      <button
                        className="btn btn-outline-secondary btn-sm"
                        onClick={() => {
                          setShowLinkExisting(!showLinkExisting);
                          setShowAddFestForm(false);
                        }}
                      >
                        <i className="bi bi-link-45deg me-1" />
                        Link Existing
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => {
                          setShowAddFestForm(!showAddFestForm);
                          setShowLinkExisting(false);
                        }}
                      >
                        <i className="bi bi-plus-lg me-1" />
                        Add Festival
                      </button>
                    </div>
                  </div>

                  {accessError && (
                    <div className="alert alert-danger py-2 mb-3" style={{ fontSize: 12 }}>
                      {accessError}
                    </div>
                  )}

                  {/* Add Festival Form */}
                  {showAddFestForm && (
                    <form
                      onSubmit={handleCreateFestival}
                      className="p-3 mb-3"
                      style={{
                        background: "rgba(255, 255, 255, 0.03)",
                        border: "1px solid var(--cc-border)",
                        borderRadius: 8,
                      }}
                    >
                      <h6 style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>
                        Add New Festival to {selectedLocation.name}
                      </h6>
                      <div className="row g-2 mb-2">
                        <div className="col-8">
                          <label className="form-label text-muted mb-1" style={{ fontSize: 11 }}>Festival Name *</label>
                          <input
                            type="text"
                            className="form-control form-control-sm"
                            placeholder="e.g. Dasara 2026"
                            value={festForm.name}
                            onChange={(e) => setFestForm({ ...festForm, name: e.target.value })}
                            required
                          />
                        </div>
                        <div className="col-4">
                          <label className="form-label text-muted mb-1" style={{ fontSize: 11 }}>Event Code *</label>
                          <input
                            type="text"
                            className="form-control form-control-sm text-uppercase"
                            placeholder="e.g. DSR-2026"
                            value={festForm.code}
                            onChange={(e) => setFestForm({ ...festForm, code: e.target.value })}
                            required
                          />
                        </div>
                      </div>

                      <div className="row g-2 mb-2">
                        <div className="col-6">
                          <label className="form-label text-muted mb-1" style={{ fontSize: 11 }}>Start Date *</label>
                          <input
                            type="datetime-local"
                            className="form-control form-control-sm"
                            value={festForm.start_date}
                            onChange={(e) => setFestForm({ ...festForm, start_date: e.target.value })}
                            required
                          />
                        </div>
                        <div className="col-6">
                          <label className="form-label text-muted mb-1" style={{ fontSize: 11 }}>End Date *</label>
                          <input
                            type="datetime-local"
                            className="form-control form-control-sm"
                            value={festForm.end_date}
                            onChange={(e) => setFestForm({ ...festForm, end_date: e.target.value })}
                            required
                          />
                        </div>
                      </div>

                      <div className="mb-2">
                        <label className="form-label text-muted mb-1" style={{ fontSize: 11 }}>Description (Optional)</label>
                        <input
                          type="text"
                          className="form-control form-control-sm"
                          placeholder="e.g. Annual celebration"
                          value={festForm.description}
                          onChange={(e) => setFestForm({ ...festForm, description: e.target.value })}
                        />
                      </div>

                      <div className="d-flex justify-content-end gap-2 mt-3">
                        <button
                          type="button"
                          className="btn btn-outline-secondary btn-sm"
                          onClick={() => setShowAddFestForm(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="btn btn-success btn-sm"
                          disabled={isSubmitting}
                        >
                          {isSubmitting ? "Creating..." : "Save Festival"}
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Link Existing Event (Safeguard #1) */}
                  {showLinkExisting && (
                    <form
                      onSubmit={handleLinkExistingEvent}
                      className="p-3 mb-3"
                      style={{
                        background: "rgba(255, 255, 255, 0.03)",
                        border: "1px solid var(--cc-border)",
                        borderRadius: 8,
                      }}
                    >
                      <h6 style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
                        Deliberate Association — Link Existing Event
                      </h6>
                      <p style={{ color: "var(--cc-text-muted)", fontSize: 11, marginBottom: 12 }}>
                        Select an existing event from the system to associate with <strong>{selectedLocation.name}</strong>.
                      </p>
                      <div className="mb-3">
                        <select
                          className="form-select form-select-sm"
                          value={selectedExistingEventId}
                          onChange={(e) => setSelectedExistingEventId(e.target.value)}
                          required
                        >
                          <option value="">-- Choose an Event to Link --</option>
                          {events.map((ev) => (
                            <option key={ev.id} value={ev.id}>
                              {ev.name} ({ev.code})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="d-flex justify-content-end gap-2">
                        <button
                          type="button"
                          className="btn btn-outline-secondary btn-sm"
                          onClick={() => setShowLinkExisting(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="btn btn-primary btn-sm"
                          disabled={isSubmitting || !selectedExistingEventId}
                        >
                          {isSubmitting ? "Linking..." : "Confirm Link"}
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Festivals List */}
                  {loadingEvents ? (
                    <div className="text-center py-4 text-muted">
                      <div className="spinner-border spinner-border-sm text-primary mb-2" role="status" />
                      <div>Loading festivals...</div>
                    </div>
                  ) : locationEvents.length === 0 ? (
                    <div className="card p-4 text-center" style={{ background: "rgba(255,255,255,0.02)", borderColor: "var(--cc-border)" }}>
                      <i className="bi bi-calendar-x mb-2" style={{ fontSize: 32, color: "var(--cc-text-muted)" }} />
                      <div style={{ fontWeight: 600 }}>No Festivals Configured for this Location</div>
                      <p style={{ color: "var(--cc-text-muted)", fontSize: 12, marginTop: 4 }}>
                        Click "+ Add Festival" above to add a festival, or "Link Existing" to associate an event.
                      </p>
                    </div>
                  ) : (
                    <div className="d-flex flex-column gap-3">
                      {locationEvents.map((fest) => {
                        const isCurrentActive = fest.id === activeEventId;
                        return (
                          <div
                            key={fest.id}
                            className="p-3"
                            style={{
                              background: isCurrentActive ? "rgba(45, 126, 247, 0.08)" : "rgba(255,255,255,0.02)",
                              border: isCurrentActive ? "1px solid var(--cc-accent)" : "1px solid var(--cc-border)",
                              borderRadius: 8,
                            }}
                          >
                            <div className="d-flex justify-content-between align-items-start">
                              <div>
                                <div className="d-flex align-items-center gap-2 mb-1">
                                  <span className={getStatusBadge(fest.status)} style={{ fontSize: 10 }}>
                                    {fest.status}
                                  </span>
                                  <span className="badge bg-dark border" style={{ fontSize: 10, borderColor: "var(--cc-border)" }}>
                                    {fest.code}
                                  </span>
                                  {isCurrentActive && (
                                    <span className="badge bg-primary" style={{ fontSize: 9 }}>
                                      CURRENT CONTEXT
                                    </span>
                                  )}
                                </div>
                                <h6 style={{ margin: "4px 0", fontWeight: 700, color: "var(--cc-text-primary)" }}>
                                  {fest.name}
                                </h6>
                                <div style={{ fontSize: 11, color: "var(--cc-text-muted)" }}>
                                  <i className="bi bi-calendar3 me-1 text-primary" />
                                  {new Date(fest.start_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
                                  {" to "}
                                  {new Date(fest.end_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
                                </div>
                              </div>

                              <button
                                className="btn btn-success btn-sm d-flex align-items-center gap-1"
                                onClick={() => handleOpenDashboard(fest)}
                                style={{ padding: "6px 14px", fontWeight: 600, fontSize: 12 }}
                              >
                                <i className="bi bi-broadcast me-1" />
                                Open
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
