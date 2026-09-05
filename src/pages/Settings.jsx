// Settings page — Phase 2: Full backend-connected configuration
import { useState, useEffect, useCallback, useRef } from 'react';
import { useSettingsStore } from '../store/useSettingsStore.js';
import * as settingsService from '../services/settingsService.js';

// ─── Common components ────────────────────────────────────────────────────────

// Input field with label
function Field({ label, value, onChange, type = 'text', readOnly = false, min, max, step, help, required }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        {label}{required && <span style={{ color: 'var(--cc-red)', marginLeft: 2 }}>*</span>}
      </label>
      <input
        type={type}
        value={value ?? ''}
        onChange={e => onChange && onChange(e.target.value)}
        readOnly={readOnly}
        min={min} max={max} step={step}
        style={{
          width: '100%', maxWidth: 400, padding: '7px 10px',
          background: readOnly ? 'var(--cc-bg-primary)' : 'var(--cc-bg-input)',
          border: '1px solid var(--cc-border)',
          borderRadius: 4, color: readOnly ? 'var(--cc-text-muted)' : 'var(--cc-text-primary)',
          fontSize: 12, outline: 'none',
        }}
      />
      {help && <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 3 }}>{help}</div>}
    </div>
  );
}

// Select field
function SelectField({ label, value, onChange, options, readOnly }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</label>
      <select
        value={value ?? ''}
        onChange={e => onChange && onChange(e.target.value)}
        disabled={readOnly}
        style={{ width: '100%', maxWidth: 400, padding: '7px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12 }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

// Threshold row
function ThresholdRow({ label, value, onChange, unit = '%', min, max, step = 1, help }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10, padding: '8px 10px', background: 'var(--cc-bg-primary)', borderRadius: 4, border: '1px solid var(--cc-border)' }}>
      <div style={{ flex: 1, fontSize: 12, color: 'var(--cc-text-secondary)' }}>
        {label}
        {help && <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 1 }}>{help}</div>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <input
          type="number"
          value={value ?? ''}
          onChange={e => onChange(parseFloat(e.target.value))}
          min={min} max={max} step={step}
          style={{ width: 80, padding: '4px 8px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12, textAlign: 'right' }}
        />
        <span style={{ fontSize: 11, color: 'var(--cc-text-muted)', minWidth: 24 }}>{unit}</span>
      </div>
    </div>
  );
}

// Toggle switch
function Toggle({ label, value, onChange, disabled, description }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, padding: '8px 12px', background: 'var(--cc-bg-primary)', border: '1px solid var(--cc-border)', borderRadius: 4 }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, color: 'var(--cc-text-primary)' }}>{label}</div>
        {description && <div style={{ fontSize: 10, color: 'var(--cc-text-muted)', marginTop: 2 }}>{description}</div>}
      </div>
      <button
        onClick={() => !disabled && onChange(!value)}
        disabled={disabled}
        style={{
          width: 40, height: 22, borderRadius: 11, border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
          background: value ? 'var(--cc-green)' : 'var(--cc-text-muted)',
          position: 'relative', transition: 'background 0.2s', flexShrink: 0,
        }}
      >
        <span style={{
          position: 'absolute', top: 3, left: value ? 20 : 3, width: 16, height: 16,
          borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
        }} />
      </button>
    </div>
  );
}

// Save/Reset button row
function SaveBar({ onSave, onReset, saving, saved, error }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--cc-border)' }}>
      <button className="cc-btn cc-btn-primary" onClick={onSave} disabled={saving} style={{ fontSize: 12, minWidth: 110 }}>
        {saving ? <><span className="spinner-border spinner-border-sm" style={{ width: 12, height: 12, marginRight: 6 }} />Saving...</> : <><i className="bi bi-save" style={{ marginRight: 5 }} />Save Changes</>}
      </button>
      <button className="cc-btn" onClick={onReset} disabled={saving} style={{ fontSize: 12 }}>Reset</button>
      {saved && <span style={{ fontSize: 11, color: 'var(--cc-green)' }}><i className="bi bi-check-circle-fill" style={{ marginRight: 4 }} />Changes saved successfully</span>}
      {error && <span style={{ fontSize: 11, color: 'var(--cc-red)' }}><i className="bi bi-exclamation-triangle-fill" style={{ marginRight: 4 }} />{error}</span>}
    </div>
  );
}

// Section header
function SectionHeader({ title, subtitle, badge }) {
  return (
    <div style={{ marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid var(--cc-border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <h5 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: 'var(--cc-text-primary)' }}>{title}</h5>
        {badge && <span className="cc-badge" style={{ fontSize: 10 }}>{badge}</span>}
      </div>
      {subtitle && <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}

// ─── Section: Event Settings ──────────────────────────────────────────────────
function EventSettingsPanel() {
  const { eventSettings, loading, loadEventSettings } = useSettingsStore();
  const [form, setForm] = useState(eventSettings || settingsService.MOCK_EVENT);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { loadEventSettings(); }, []);
  useEffect(() => { if (eventSettings) setForm({ ...eventSettings }); }, [eventSettings]);

  const handleSave = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      await settingsService.updateEventSettings(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) { setError(e.message || 'Save failed'); }
    finally { setSaving(false); }
  };

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  if (loading.event && !form) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading event configuration...</div>;
  if (!form) return null;

  return (
    <div>
      <SectionHeader title="Event Settings" subtitle="Configure the active festival event" badge={form.status} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
        <Field label="Event Name" value={form.name} onChange={v => set('name', v)} required />
        <Field label="Event Code" value={form.code} readOnly />
        <Field label="Year" value={form.year} type="number" onChange={v => set('year', parseInt(v))} />
        <SelectField label="Status" value={form.status} onChange={v => set('status', v)}
          options={['PLANNING','ACTIVE','SUSPENDED','COMPLETED'].map(s => ({ value: s, label: s }))} />
        <Field label="Start Date" value={form.start_date?.slice(0,10)} type="date" onChange={v => set('start_date', v)} />
        <Field label="End Date" value={form.end_date?.slice(0,10)} type="date" onChange={v => set('end_date', v)} />
        <Field label="Timezone" value={form.timezone} onChange={v => set('timezone', v)} />
      </div>
      <div style={{ marginBottom: 14 }}>
        <label style={{ display: 'block', fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>Description</label>
        <textarea value={form.description ?? ''} onChange={e => set('description', e.target.value)}
          rows={3} style={{ width: '100%', maxWidth: 600, padding: '7px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12, resize: 'vertical' }} />
      </div>
      <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 12 }}>
        Last updated: {new Date(form.updated_at || Date.now()).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
      </div>
      <SaveBar onSave={handleSave} onReset={() => setForm({ ...eventSettings })} saving={saving} saved={saved} error={error} />
    </div>
  );
}

// ─── Section: Zone Settings ───────────────────────────────────────────────────
function ZoneSettingsPanel() {
  const { zoneSettings, loading, loadZoneSettings } = useSettingsStore();
  const [search, setSearch] = useState('');
  const [editZone, setEditZone] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { if (!zoneSettings.length) loadZoneSettings(); }, []);

  const filtered = zoneSettings.filter(z =>
    z.zone_code?.toLowerCase().includes(search.toLowerCase()) ||
    z.name?.toLowerCase().includes(search.toLowerCase())
  );

  const openEdit = (zone) => { setEditZone(zone); setEditForm({ ...zone }); setSaved(false); setError(null); };
  const closeEdit = () => { setEditZone(null); setEditForm({}); };

  const handleSave = async () => {
    setSaving(true); setError(null);
    try {
      await settingsService.updateZoneSetting(editZone.zone_code, editForm);
      setSaved(true);
      setTimeout(() => { setSaved(false); closeEdit(); }, 1500);
      loadZoneSettings();
    } catch (e) { setError(e.message || 'Save failed'); }
    finally { setSaving(false); }
  };

  const riskBadgeColor = (r) => ({ CRITICAL: 'var(--cc-red)', HIGH: 'var(--cc-orange)', MEDIUM: 'var(--cc-yellow)', LOW: 'var(--cc-green)' }[r] || 'var(--cc-text-muted)');

  if (loading.zones) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading zones...</div>;

  return (
    <div>
      <SectionHeader title="Zone Settings" subtitle="Manage operational zone configuration, capacity, and risk thresholds" />
      <div style={{ marginBottom: 12 }}>
        <input placeholder="Search zone..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '6px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12, width: 240 }} />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="cc-table" style={{ fontSize: 12 }}>
          <thead><tr><th>Code</th><th>Name</th><th>Capacity</th><th>Current</th><th>Risk</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(z => (
              <tr key={z.zone_code}>
                <td style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11 }}>{z.zone_code}</td>
                <td>{z.name}</td>
                <td style={{ fontFamily: 'var(--cc-font-mono)' }}>{z.capacity?.toLocaleString()}</td>
                <td style={{ fontFamily: 'var(--cc-font-mono)' }}>{z.current_people?.toLocaleString()}</td>
                <td><span style={{ fontSize: 10, fontWeight: 700, color: riskBadgeColor(z.risk_level), background: `${riskBadgeColor(z.risk_level)}22`, padding: '2px 8px', borderRadius: 3 }}>{z.risk_level}</span></td>
                <td><span style={{ fontSize: 10, color: z.status === 'ACTIVE' ? 'var(--cc-green)' : 'var(--cc-text-muted)' }}>{z.status}</span></td>
                <td><button className="cc-btn" style={{ fontSize: 10, padding: '3px 10px' }} onClick={() => openEdit(z)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Edit Modal */}
      {editZone && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--cc-bg-card)', border: '1px solid var(--cc-border)', borderRadius: 8, padding: 24, width: 520, maxHeight: '85vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h6 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Edit Zone  {editZone.zone_code}</h6>
              <button onClick={closeEdit} style={{ background: 'none', border: 'none', color: 'var(--cc-text-muted)', fontSize: 18, cursor: 'pointer' }}>×</button>
            </div>
            <Field label="Zone Name" value={editForm.name} onChange={v => setEditForm(f => ({ ...f, name: v }))} />
            <Field label="Label" value={editForm.label} onChange={v => setEditForm(f => ({ ...f, label: v }))} />
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>Description</label>
              <textarea value={editForm.description ?? ''} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                rows={2} style={{ width: '100%', padding: '7px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12, resize: 'vertical' }} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
              <Field label="Maximum Capacity" value={editForm.capacity} type="number" onChange={v => setEditForm(f => ({ ...f, capacity: parseInt(v) }))} />
              <SelectField label="Risk Level" value={editForm.risk_level} onChange={v => setEditForm(f => ({ ...f, risk_level: v }))}
                options={['LOW','MEDIUM','HIGH','CRITICAL'].map(v => ({ value: v, label: v }))} />
              <SelectField label="Status" value={editForm.status} onChange={v => setEditForm(f => ({ ...f, status: v }))}
                options={['ACTIVE','INACTIVE','MAINTENANCE'].map(v => ({ value: v, label: v }))} />
            </div>
            {error && <div style={{ fontSize: 11, color: 'var(--cc-red)', marginBottom: 10 }}>{error}</div>}
            {saved && <div style={{ fontSize: 11, color: 'var(--cc-green)', marginBottom: 10 }}>✓ Saved successfully</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, borderTop: '1px solid var(--cc-border)', paddingTop: 14 }}>
              <button className="cc-btn" onClick={closeEdit}>Cancel</button>
              <button className="cc-btn cc-btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Zone'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Section: Camera Settings ─────────────────────────────────────────────────
function CameraSettingsPanel() {
  const { cameraSettings, loading, loadCameraSettings } = useSettingsStore();
  const [search, setSearch] = useState('');
  const [filterZone, setFilterZone] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [editCam, setEditCam] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => { if (!cameraSettings.length) loadCameraSettings(); }, []);

  const zones = [...new Set(cameraSettings.map(c => c.zone_code).filter(Boolean))];

  const filtered = cameraSettings.filter(c => {
    const q = search.toLowerCase();
    return (!search || c.camera_code?.toLowerCase().includes(q) || c.name?.toLowerCase().includes(q)) &&
      (!filterZone || c.zone_code === filterZone) &&
      (!filterStatus || c.status === filterStatus);
  });

  const openEdit = (cam) => { setEditCam(cam); setEditForm({ ...cam }); setSaved(false); setError(null); setTestResult(null); };
  const closeEdit = () => { setEditCam(null); setEditForm({}); };

  const handleSave = async () => {
    setSaving(true); setError(null);
    try {
      await settingsService.updateCameraSetting(editCam.camera_code, editForm);
      setSaved(true);
      setTimeout(() => { setSaved(false); closeEdit(); }, 1500);
      loadCameraSettings();
    } catch (e) { setError(e.message || 'Save failed'); }
    finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const result = await settingsService.testCameraConnection(editCam.camera_code);
      setTestResult(result);
    } catch (e) { setTestResult({ connection_status: 'FAILED', message: e.message }); }
    finally { setTesting(false); }
  };

  const statusColor = (s) => ({ online: 'var(--cc-green)', offline: 'var(--cc-red)', degraded: 'var(--cc-yellow)' }[s] || 'var(--cc-text-muted)');

  if (loading.cameras) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading cameras...</div>;

  return (
    <div>
      <SectionHeader title="Camera Settings" subtitle="Configure cameras, AI toggles, FRS channels, and RTSP connections" />
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <input placeholder="Search camera..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '6px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12, width: 200 }} />
        <select value={filterZone} onChange={e => setFilterZone(e.target.value)}
          style={{ padding: '6px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12 }}>
          <option value="">All Zones</option>
          {zones.map(z => <option key={z} value={z}>{z}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          style={{ padding: '6px 10px', background: 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12 }}>
          <option value="">All Status</option>
          <option value="online">Online</option>
          <option value="offline">Offline</option>
          <option value="degraded">Degraded</option>
        </select>
        <span style={{ fontSize: 11, color: 'var(--cc-text-muted)', alignSelf: 'center' }}>Showing {filtered.length} of {cameraSettings.length}</span>
      </div>
      <div style={{ overflowX: 'auto', maxHeight: 400, overflowY: 'auto' }}>
        <table className="cc-table" style={{ fontSize: 11 }}>
          <thead><tr><th>Camera ID</th><th>Name</th><th>Zone</th><th>Type</th><th>FPS</th><th>Resolution</th><th>FRS</th><th>PTZ</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(c => (
              <tr key={c.camera_code}>
                <td style={{ fontFamily: 'var(--cc-font-mono)' }}>{c.camera_code}</td>
                <td>{c.name}</td>
                <td style={{ fontSize: 10 }}>{c.zone_code}</td>
                <td><span style={{ fontSize: 9, background: 'var(--cc-accent-dim)', color: 'var(--cc-blue)', padding: '2px 6px', borderRadius: 3 }}>{c.camera_type}</span></td>
                <td style={{ fontFamily: 'var(--cc-font-mono)' }}>{c.fps}</td>
                <td style={{ fontSize: 10 }}>{c.resolution}</td>
                <td><span style={{ color: c.is_frs_camera ? 'var(--cc-green)' : 'var(--cc-text-muted)', fontSize: 10 }}>{c.is_frs_camera ? 'ON' : 'OFF'}</span></td>
                <td><span style={{ color: c.is_ptz ? 'var(--cc-blue)' : 'var(--cc-text-muted)', fontSize: 10 }}>{c.is_ptz ? 'YES' : 'NO'}</span></td>
                <td><span style={{ color: statusColor(c.status), fontSize: 10, fontWeight: 600 }}>{c.status?.toUpperCase()}</span></td>
                <td><button className="cc-btn" style={{ fontSize: 10, padding: '2px 8px' }} onClick={() => openEdit(c)}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Edit Modal */}
      {editCam && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--cc-bg-card)', border: '1px solid var(--cc-border)', borderRadius: 8, padding: 24, width: 560, maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h6 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Edit Camera  {editCam.camera_code}</h6>
              <button onClick={closeEdit} style={{ background: 'none', border: 'none', color: 'var(--cc-text-muted)', fontSize: 18, cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
              <Field label="Camera Name" value={editForm.name} onChange={v => setEditForm(f => ({ ...f, name: v }))} />
              <Field label="Camera Code" value={editForm.camera_code} readOnly />
              <SelectField label="Camera Type" value={editForm.camera_type} onChange={v => setEditForm(f => ({ ...f, camera_type: v }))}
                options={['CROWD','FRS','PTZ','STATIC'].map(v => ({ value: v, label: v }))} />
              <Field label="Zone Code" value={editForm.zone_code} onChange={v => setEditForm(f => ({ ...f, zone_code: v }))} />
              <SelectField label="Resolution" value={editForm.resolution} onChange={v => setEditForm(f => ({ ...f, resolution: v }))}
                options={['4K','1080p','720p','480p'].map(v => ({ value: v, label: v }))} />
              <Field label="FPS" value={editForm.fps} type="number" min={1} max={60} onChange={v => setEditForm(f => ({ ...f, fps: parseInt(v) }))} />
              <SelectField label="Status" value={editForm.status} onChange={v => setEditForm(f => ({ ...f, status: v }))}
                options={['online','offline','degraded'].map(v => ({ value: v, label: v }))} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
              {[['FRS Camera', 'is_frs_camera'], ['PTZ Enabled', 'is_ptz']].map(([label, key]) => (
                <Toggle key={key} label={label} value={editForm[key]} onChange={v => setEditForm(f => ({ ...f, [key]: v }))} />
              ))}
            </div>
            {/* RTSP credential block */}
            <div style={{ background: 'var(--cc-bg-primary)', border: '1px solid var(--cc-border)', borderRadius: 6, padding: 12, marginBottom: 14 }}>
              <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <i className="bi bi-lock-fill" style={{ color: 'var(--cc-orange)' }} />
                RTSP Credentials  Protected
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--cc-text-secondary)', flex: 1 }}>Current RTSP URL</span>
                <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 13, color: 'var(--cc-text-muted)', letterSpacing: '0.1em' }}>
                  {editForm.has_rtsp_configured ? '••••••••••••••••' : 'Not configured'}
                </span>
              </div>
              <Field label="New RTSP URL (leave blank to keep existing)" value={editForm.rtsp_url ?? ''}
                onChange={v => setEditForm(f => ({ ...f, rtsp_url: v || undefined }))}
                help="rtsp://username:password@ip:port/stream" />
            </div>
            {/* Camera test */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              <button className="cc-btn" onClick={handleTest} disabled={testing} style={{ fontSize: 11 }}>
                {testing ? <><span className="spinner-border spinner-border-sm" style={{ width: 10, height: 10, marginRight: 5 }} />Testing...</> : <><i className="bi bi-wifi" style={{ marginRight: 4 }} />Test Connection</>}
              </button>
              {testResult && (
                <span style={{ fontSize: 11, color: testResult.connection_status === 'ONLINE' ? 'var(--cc-green)' : 'var(--cc-red)', alignSelf: 'center' }}>
                  {testResult.connection_status === 'ONLINE'
                    ? `✓ Online  ${testResult.latency_ms}ms  ${testResult.fps}fps`
                    : `✗ ${testResult.message}`}
                </span>
              )}
            </div>
            {error && <div style={{ fontSize: 11, color: 'var(--cc-red)', marginBottom: 8 }}>{error}</div>}
            {saved && <div style={{ fontSize: 11, color: 'var(--cc-green)', marginBottom: 8 }}>✓ Saved successfully</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12, borderTop: '1px solid var(--cc-border)', paddingTop: 14 }}>
              <button className="cc-btn" onClick={closeEdit}>Cancel</button>
              <button className="cc-btn cc-btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Camera'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Section: Alert Thresholds ────────────────────────────────────────────────
function AlertThresholdsPanel() {
  const { alertSettings, loading, loadAlertSettings } = useSettingsStore();
  const [form, setForm] = useState(alertSettings || settingsService.MOCK_ALERT_THRESHOLDS);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { loadAlertSettings(); }, []);
  useEffect(() => { if (alertSettings) setForm({ ...alertSettings }); }, [alertSettings]);

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  const handleSave = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      // Validate order
      if (form.crowd_high_pct <= form.crowd_warning_pct) throw new Error('High threshold must exceed warning threshold');
      if (form.crowd_critical_pct <= form.crowd_high_pct) throw new Error('Critical threshold must exceed high threshold');
      if (form.queue_critical_count <= form.queue_warning_count) throw new Error('Critical queue count must exceed warning count');
      await settingsService.updateAlertSettings(form);
      setSaved(true); setTimeout(() => setSaved(false), 3000);
    } catch (e) { setError(e.message || 'Save failed'); }
    finally { setSaving(false); }
  };

  const handleReset = async () => {
    setSaving(true);
    const def = await settingsService.resetAlertSettings();
    setForm({ ...def });
    setSaving(false);
  };

  if (loading.alerts && !form) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading thresholds...</div>;
  if (!form) return null;

  const Section = ({ title }) => (
    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, marginTop: 16, paddingBottom: 4, borderBottom: '1px solid var(--cc-border)' }}>{title}</div>
  );

  return (
    <div>
      <SectionHeader title="Alert Thresholds" subtitle="Configure density, queue, flow, and AI risk thresholds" badge={`v${form.config_version || 1}`} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
        <div>
          <Section title="Crowd Density" />
          <ThresholdRow label="Warning" value={form.crowd_warning_pct} onChange={v => set('crowd_warning_pct', v)} unit="%" min={50} max={100} step={0.5} />
          <ThresholdRow label="High" value={form.crowd_high_pct} onChange={v => set('crowd_high_pct', v)} unit="%" min={60} max={120} step={0.5} />
          <ThresholdRow label="Critical" value={form.crowd_critical_pct} onChange={v => set('crowd_critical_pct', v)} unit="%" min={70} max={150} step={0.5} />
          <ThresholdRow label="Extreme" value={form.crowd_extreme_pct} onChange={v => set('crowd_extreme_pct', v)} unit="%" min={80} max={200} step={0.5} />

          <Section title="Crowd Flow" />
          <ThresholdRow label="Sudden Inflow Increase" value={form.sudden_inflow_pct} onChange={v => set('sudden_inflow_pct', v)} unit="%" min={5} max={200} />
          <ThresholdRow label="Reverse Flow Threshold" value={form.reverse_flow_pct} onChange={v => set('reverse_flow_pct', v)} unit="%" min={5} max={100} />
          <ThresholdRow label="Density Growth Rate" value={form.density_growth_rate_pct} onChange={v => set('density_growth_rate_pct', v)} unit="%/min" min={1} max={100} />
        </div>
        <div>
          <Section title="Queue Management" />
          <ThresholdRow label="Queue Length Warning" value={form.queue_warning_count} onChange={v => set('queue_warning_count', v)} unit="pax" min={50} max={5000} step={10} />
          <ThresholdRow label="Queue Length Critical" value={form.queue_critical_count} onChange={v => set('queue_critical_count', v)} unit="pax" min={100} max={10000} step={10} />
          <ThresholdRow label="Max Wait Warning" value={form.queue_wait_warning_min} onChange={v => set('queue_wait_warning_min', v)} unit="min" min={1} max={120} />
          <ThresholdRow label="Max Wait Critical" value={form.queue_wait_critical_min} onChange={v => set('queue_wait_critical_min', v)} unit="min" min={5} max={240} />

          <Section title="AI Event Thresholds" />
          <ThresholdRow label="Camera Offline Detection" value={form.camera_offline_sec} onChange={v => set('camera_offline_sec', v)} unit="sec" min={5} max={300} />
          <ThresholdRow label="Camera Degraded Trigger" value={form.camera_degraded_sec} onChange={v => set('camera_degraded_sec', v)} unit="sec" min={1} max={60} />
          <ThresholdRow label="Person Down Duration" value={form.person_down_sec} onChange={v => set('person_down_sec', v)} unit="sec" min={3} max={60} />
          <ThresholdRow label="Panic Risk Score" value={form.panic_risk_score} onChange={v => set('panic_risk_score', v)} unit="score" min={0} max={1} step={0.01} />
          <ThresholdRow label="Bottleneck Risk Score" value={form.bottleneck_risk_score} onChange={v => set('bottleneck_risk_score', v)} unit="score" min={0} max={1} step={0.01} />
        </div>
      </div>
      {error && <div style={{ marginTop: 8, padding: '8px 12px', background: 'var(--cc-red-dim, rgba(248,81,73,0.1))', border: '1px solid var(--cc-red)', borderRadius: 4, fontSize: 11, color: 'var(--cc-red)' }}>{error}</div>}
      <SaveBar onSave={handleSave} onReset={handleReset} saving={saving} saved={saved} error={null} />
    </div>
  );
}

// ─── Section: User Roles ──────────────────────────────────────────────────────
function UserRolesPanel() {
  const { roles, permissions, loading, loadRoles } = useSettingsStore();
  const [editRole, setEditRole] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [selectedPerms, setSelectedPerms] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { loadRoles(); }, []);

  const openEdit = (role) => {
    setEditRole(role);
    setEditForm({ name: role.name, description: role.description });
    setSelectedPerms(role.permissions?.map(p => p.code) ?? []);
    setSaved(false); setError(null);
  };
  const closeEdit = () => { setEditRole(null); };

  const togglePerm = (code) => setSelectedPerms(p => p.includes(code) ? p.filter(x => x !== code) : [...p, code]);

  const handleSave = async () => {
    if (editRole?.is_system_role && editRole?.code === 'SUPER_ADMIN') {
      setError('Super Admin role is protected. Permissions cannot be modified.');
      return;
    }
    setSaving(true); setError(null);
    try {
      await settingsService.updateRole(editRole.id, editForm);
      await settingsService.updateRolePermissions(editRole.id, selectedPerms);
      setSaved(true);
      setTimeout(() => { setSaved(false); closeEdit(); }, 1500);
      loadRoles();
    } catch (e) { setError(e.message || 'Save failed'); }
    finally { setSaving(false); }
  };

  // Group permissions by module
  const permGroups = {};
  permissions.forEach(p => {
    const [module] = p.code.split(':');
    if (!permGroups[module]) permGroups[module] = [];
    permGroups[module].push(p);
  });

  if (loading.roles) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading roles...</div>;

  return (
    <div>
      <SectionHeader title="User Roles" subtitle="Manage role definitions and permission assignments" />
      <table className="cc-table" style={{ fontSize: 12 }}>
        <thead><tr><th>Role Name</th><th>Code</th><th>Users</th><th>Type</th><th>Actions</th></tr></thead>
        <tbody>
          {roles.map(r => (
            <tr key={r.id}>
              <td style={{ fontWeight: 600 }}>{r.name}</td>
              <td style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11 }}>{r.code}</td>
              <td style={{ fontFamily: 'var(--cc-font-mono)' }}>{r.user_count}</td>
              <td>
                {r.is_system_role
                  ? <span style={{ fontSize: 10, color: 'var(--cc-orange)', background: 'rgba(210,153,34,0.15)', padding: '2px 8px', borderRadius: 3 }}>🔒 SYSTEM</span>
                  : <span style={{ fontSize: 10, color: 'var(--cc-green)', background: 'rgba(63,185,80,0.1)', padding: '2px 8px', borderRadius: 3 }}>Active</span>}
              </td>
              <td><button className="cc-btn" style={{ fontSize: 10, padding: '3px 10px' }} onClick={() => openEdit(r)}>{r.is_system_role ? 'View' : 'Edit'}</button></td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Role Edit Modal */}
      {editRole && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--cc-bg-card)', border: '1px solid var(--cc-border)', borderRadius: 8, padding: 24, width: 680, maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h6 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Edit Role  {editRole.name}</h6>
              <button onClick={closeEdit} style={{ background: 'none', border: 'none', color: 'var(--cc-text-muted)', fontSize: 18, cursor: 'pointer' }}>×</button>
            </div>
            {editRole.is_system_role && (
              <div style={{ padding: '10px 14px', background: 'rgba(210,153,34,0.1)', border: '1px solid var(--cc-orange)', borderRadius: 6, marginBottom: 16, fontSize: 11, color: 'var(--cc-orange)' }}>
                <i className="bi bi-lock-fill" style={{ marginRight: 6 }} />
                Protected System Role  Permission changes restricted
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px', marginBottom: 16 }}>
              <Field label="Role Name" value={editForm.name} onChange={v => setEditForm(f => ({ ...f, name: v }))} readOnly={editRole.is_system_role} />
              <Field label="Role Code" value={editRole.code} readOnly />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 11, color: 'var(--cc-text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>Description</label>
              <textarea value={editForm.description ?? ''} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                rows={2} readOnly={editRole.is_system_role}
                style={{ width: '100%', padding: '7px 10px', background: editRole.is_system_role ? 'var(--cc-bg-primary)' : 'var(--cc-bg-input)', border: '1px solid var(--cc-border)', borderRadius: 4, color: 'var(--cc-text-primary)', fontSize: 12, resize: 'vertical' }} />
            </div>

            {/* Permission Matrix */}
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, borderBottom: '1px solid var(--cc-border)', paddingBottom: 8 }}>Permissions</div>
            {!editRole.is_system_role && (
              <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                <button className="cc-btn" style={{ fontSize: 10 }} onClick={() => setSelectedPerms(permissions.map(p => p.code))}>Select All</button>
                <button className="cc-btn" style={{ fontSize: 10 }} onClick={() => setSelectedPerms([])}>Clear All</button>
              </div>
            )}
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {Object.entries(permGroups).map(([module, perms]) => (
                <div key={module} style={{ marginBottom: 8, padding: '8px 10px', background: 'var(--cc-bg-primary)', borderRadius: 4, border: '1px solid var(--cc-border)' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-secondary)', textTransform: 'uppercase', marginBottom: 6 }}>{module}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {perms.map(p => (
                      <label key={p.code} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--cc-text-secondary)', cursor: editRole.is_system_role ? 'not-allowed' : 'pointer' }}>
                        <input type="checkbox" checked={selectedPerms.includes(p.code)}
                          onChange={() => !editRole.is_system_role && togglePerm(p.code)}
                          disabled={editRole.is_system_role}
                          style={{ accentColor: 'var(--cc-accent)' }} />
                        {p.code.split(':')[1]}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {error && <div style={{ fontSize: 11, color: 'var(--cc-red)', marginTop: 8 }}>{error}</div>}
            {saved && <div style={{ fontSize: 11, color: 'var(--cc-green)', marginTop: 8 }}>✓ Role updated successfully</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16, borderTop: '1px solid var(--cc-border)', paddingTop: 14 }}>
              <button className="cc-btn" onClick={closeEdit}>Cancel</button>
              {!editRole.is_system_role && (
                <button className="cc-btn cc-btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Role'}</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Section: Notifications ───────────────────────────────────────────────────
function NotificationsPanel() {
  const { notificationSettings, loading, loadNotificationSettings } = useSettingsStore();
  const [form, setForm] = useState(notificationSettings || settingsService.MOCK_NOTIFICATION_CONFIG);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { loadNotificationSettings(); }, []);
  useEffect(() => { if (notificationSettings) setForm({ ...notificationSettings }); }, [notificationSettings]);

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  const handleSave = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      await settingsService.updateNotificationSettings(form);
      setSaved(true); setTimeout(() => setSaved(false), 3000);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  if (loading.notifications && !form) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading notifications...</div>;
  if (!form) return null;

  return (
    <div>
      <SectionHeader title="Notification Settings" subtitle="Configure alert channels and delivery preferences" />
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Channels</div>
      <Toggle label="In-App Notifications" value={form.inapp_enabled} onChange={v => set('inapp_enabled', v)} description="Real-time alerts in the command center interface" />
      <Toggle label="Email Notifications" value={form.email_enabled} onChange={v => set('email_enabled', v)} description="Send alert emails to configured recipients" />
      <Toggle label="SMS Notifications" value={form.sms_enabled} onChange={v => set('sms_enabled', v)} description="SMS alerts for critical incidents" />
      <Toggle label="WebSocket Real-Time Events" value={form.websocket_enabled} onChange={v => set('websocket_enabled', v)} description="Real-time push to all connected clients" />
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10, marginTop: 20 }}>Delivery Priority</div>
      <Toggle label="Critical Alerts" value={form.critical_immediate} onChange={v => set('critical_immediate', v)} description="Immediate  no batching or delay" />
      <Toggle label="High Alerts" value={form.high_immediate} onChange={v => set('high_immediate', v)} description="Immediate dispatch" />
      <Toggle label="Medium Alerts" value={form.medium_grouped} onChange={v => set('medium_grouped', v)} description="Grouped  delivered in batches every 5 minutes" />
      <Toggle label="Low Alerts" value={form.low_summary} onChange={v => set('low_summary', v)} description="Summary mode  daily digest" />
      <SaveBar onSave={handleSave} onReset={() => setForm({ ...notificationSettings })} saving={saving} saved={saved} error={error} />
    </div>
  );
}

// ─── Section: AI Configuration ────────────────────────────────────────────────
function AIConfigPanel() {
  const { aiSettings, loading, loadAISettings } = useSettingsStore();
  const [form, setForm] = useState(aiSettings || settingsService.MOCK_AI_CONFIG);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { loadAISettings(); }, []);
  useEffect(() => { if (aiSettings) setForm({ ...aiSettings }); }, [aiSettings]);

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  const handleSave = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      await settingsService.updateAISettings(form);
      setSaved(true); setTimeout(() => setSaved(false), 3000);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  if (loading.ai && !form) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading AI configuration...</div>;
  if (!form) return null;

  return (
    <div>
      <SectionHeader title="AI Configuration" subtitle="Configure crowd AI detection, model parameters, and video intelligence" />
      <div style={{ padding: '10px 14px', background: 'rgba(88,166,255,0.08)', border: '1px solid rgba(88,166,255,0.2)', borderRadius: 6, marginBottom: 16, fontSize: 11, color: 'var(--cc-blue)' }}>
        <i className="bi bi-cpu-fill" style={{ marginRight: 6 }} />
        AI Engine: Phase 3  Model configurations are applied when the inference engine is connected.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Crowd AI</div>
          <Toggle label="Crowd Detection" value={form.crowd_detection_enabled} onChange={v => set('crowd_detection_enabled', v)} description="Enable YOLO-based people detection" />
          <Toggle label="People Counting" value={form.people_counting_enabled} onChange={v => set('people_counting_enabled', v)} />
          <Toggle label="Queue Detection" value={form.queue_detection_enabled} onChange={v => set('queue_detection_enabled', v)} />
          <div style={{ marginTop: 12 }}>
            <Field label="Model Name" value={form.model_name} onChange={v => set('model_name', v)} />
            <Field label="Model Version" value={form.model_version} onChange={v => set('model_version', v)} />
            <Field label="Tracking Algorithm" value={form.tracking_algorithm} onChange={v => set('tracking_algorithm', v)} help="ByteTrack / DeepSORT / SORT" />
          </div>
          <ThresholdRow label="Detection Confidence" value={form.detection_confidence} onChange={v => set('detection_confidence', v)} unit="score" min={0} max={1} step={0.01} help="Min: 0.0, Max: 1.0" />
          <ThresholdRow label="Processing FPS" value={form.processing_fps} onChange={v => set('processing_fps', parseInt(v))} unit="fps" min={1} max={30} help="Frames per second processed by AI" />
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Video Intelligence</div>
          <Toggle label="Bottleneck Detection" value={form.bottleneck_detection_enabled} onChange={v => set('bottleneck_detection_enabled', v)} />
          <Toggle label="Reverse Flow Detection" value={form.reverse_flow_detection_enabled} onChange={v => set('reverse_flow_detection_enabled', v)} />
          <Toggle label="Fall / Person Down Detection" value={form.fall_detection_enabled} onChange={v => set('fall_detection_enabled', v)} />
          <Toggle label="Panic Risk Detection" value={form.panic_risk_detection_enabled} onChange={v => set('panic_risk_detection_enabled', v)} />
        </div>
      </div>
      <SaveBar onSave={handleSave} onReset={() => setForm({ ...aiSettings })} saving={saving} saved={saved} error={error} />
    </div>
  );
}

// ─── Section: FRS Configuration ───────────────────────────────────────────────
function FRSConfigPanel() {
  const { frsSettings, loading, loadFRSSettings } = useSettingsStore();
  const [form, setForm] = useState(frsSettings || settingsService.MOCK_FRS_CONFIG);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { loadFRSSettings(); }, []);
  useEffect(() => { if (frsSettings) setForm({ ...frsSettings }); }, [frsSettings]);

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  const handleSave = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      if (form.candidate_threshold > form.match_threshold) {
        throw new Error('Candidate threshold cannot be greater than match threshold');
      }
      await settingsService.updateFRSSettings(form);
      setSaved(true); setTimeout(() => setSaved(false), 3000);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  if (loading.frs && !form) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading FRS configuration...</div>;
  if (!form) return null;

  return (
    <div>
      <SectionHeader title="FRS Configuration" subtitle="Facial recognition system detection and matching configuration" />
      <div style={{ padding: '12px 16px', background: 'rgba(210,153,34,0.1)', border: '1px solid rgba(210,153,34,0.4)', borderRadius: 6, marginBottom: 18, display: 'flex', alignItems: 'center', gap: 10 }}>
        <i className="bi bi-shield-lock-fill" style={{ color: 'var(--cc-orange)', fontSize: 18 }} />
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cc-orange)' }}>🔒 HUMAN REVIEW REQUIRED</div>
          <div style={{ fontSize: 11, color: 'var(--cc-text-muted)', marginTop: 2 }}>Auto-confirmation is DISABLED. All FRS candidates require authorized human review. This setting cannot be changed.</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Detection</div>
          <Toggle label="Face Detection" value={form.face_detection_enabled} onChange={v => set('face_detection_enabled', v)} />
          <ThresholdRow label="Minimum Face Size" value={form.min_face_size} onChange={v => set('min_face_size', parseInt(v))} unit="px" min={20} max={500} />
          <ThresholdRow label="Face Quality Threshold" value={form.face_quality_threshold} onChange={v => set('face_quality_threshold', v)} unit="score" min={0} max={1} step={0.01} />

          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10, marginTop: 16 }}>Matching</div>
          <ThresholdRow label="Match Threshold" value={(form.match_threshold * 100).toFixed(0)} onChange={v => set('match_threshold', v / 100)} unit="%" min={50} max={100} help="Minimum confidence for watchlist match" />
          <ThresholdRow label="Candidate Threshold" value={(form.candidate_threshold * 100).toFixed(0)} onChange={v => set('candidate_threshold', v / 100)} unit="%" min={30} max={100} help="Must be less than match threshold" />
          <ThresholdRow label="Max Candidates" value={form.max_candidates} onChange={v => set('max_candidates', parseInt(v))} unit="" min={1} max={20} />
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Access Control</div>
          <Toggle label="Watchlist Access" value={form.watchlist_access_enabled} onChange={v => set('watchlist_access_enabled', v)} />
          <Toggle label="Missing Person Search" value={form.missing_person_access_enabled} onChange={v => set('missing_person_access_enabled', v)} />
          <Toggle label="Human Review Required" value={true} disabled description="Cannot be disabled  policy enforced" />
          <Toggle label="Auto Confirmation" value={false} disabled description="Cannot be enabled  policy enforced" />

          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10, marginTop: 16 }}>Data Retention</div>
          <ThresholdRow label="Candidate Retention" value={form.candidate_retention_days} onChange={v => set('candidate_retention_days', parseInt(v))} unit="days" min={1} max={365} />
          <ThresholdRow label="Image Retention" value={form.image_retention_days} onChange={v => set('image_retention_days', parseInt(v))} unit="days" min={1} max={730} />
          <ThresholdRow label="Audit Log Retention" value={form.audit_retention_days} onChange={v => set('audit_retention_days', parseInt(v))} unit="days" min={30} max={2555} />
        </div>
      </div>
      {error && <div style={{ marginTop: 8, padding: '8px 12px', background: 'rgba(248,81,73,0.1)', border: '1px solid var(--cc-red)', borderRadius: 4, fontSize: 11, color: 'var(--cc-red)' }}>{error}</div>}
      <SaveBar onSave={handleSave} onReset={() => setForm({ ...frsSettings })} saving={saving} saved={saved} error={null} />
    </div>
  );
}

// ─── Section: System Settings ─────────────────────────────────────────────────
function SystemSettingsPanel() {
  const { systemSettings, loading, loadSystemSettings } = useSettingsStore();
  const [form, setForm] = useState(systemSettings || settingsService.MOCK_SYSTEM_CONFIG);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [maintenanceConfirm, setMaintenanceConfirm] = useState(false);

  useEffect(() => { loadSystemSettings(); }, []);
  useEffect(() => { if (systemSettings) setForm({ ...systemSettings }); }, [systemSettings]);

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }));

  const handleSave = async () => {
    setSaving(true); setSaved(false); setError(null);
    try {
      await settingsService.updateSystemSettings(form);
      setSaved(true); setTimeout(() => setSaved(false), 3000);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const handleMaintenance = async () => {
    if (!maintenanceConfirm) { setMaintenanceConfirm(true); return; }
    setSaving(true);
    try {
      const updated = await settingsService.setMaintenanceMode(!form.maintenance_mode, form.maintenance_message);
      setForm(f => ({ ...f, maintenance_mode: !f.maintenance_mode }));
      setMaintenanceConfirm(false);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  if (loading.system && !form) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--cc-text-muted)' }}><span className="spinner-border spinner-border-sm" style={{ marginRight: 8 }} />Loading system configuration...</div>;
  if (!form) return null;

  return (
    <div>
      <SectionHeader title="System Settings" subtitle="Application configuration, runtime options, and system status" />
      {form.maintenance_mode && (
        <div style={{ padding: '12px 16px', background: 'rgba(248,81,73,0.1)', border: '1px solid var(--cc-red)', borderRadius: 6, marginBottom: 16, fontSize: 12, color: 'var(--cc-red)', fontWeight: 700 }}>
          ⚠ SYSTEM MAINTENANCE MODE ACTIVE
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Application</div>
          <Field label="Application Name" value={form.app_name} onChange={v => set('app_name', v)} />
          <Field label="Version" value={form.app_version} readOnly />
          <SelectField label="Environment" value={form.environment} onChange={v => set('environment', v)}
            options={['production','staging','development'].map(v => ({ value: v, label: v }))} />
          <Field label="Timezone" value={form.timezone} onChange={v => set('timezone', v)} />

          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10, marginTop: 16 }}>Real-Time</div>
          <Toggle label="WebSocket Enabled" value={form.websocket_enabled} onChange={v => set('websocket_enabled', v)} />
          <Toggle label="Redis Pub/Sub Enabled" value={form.redis_pubsub_enabled} onChange={v => set('redis_pubsub_enabled', v)} />
          <ThresholdRow label="Event Retention" value={form.event_retention_days} onChange={v => set('event_retention_days', parseInt(v))} unit="days" min={1} max={365} />
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>System Status</div>
          {[
            ['Database', 'PostgreSQL', 'var(--cc-green)'],
            ['Redis', 'Connected', 'var(--cc-green)'],
            ['WebSocket', form.websocket_enabled ? 'Active' : 'Disabled', form.websocket_enabled ? 'var(--cc-green)' : 'var(--cc-text-muted)'],
            ['AI Engine', 'Phase 3', 'var(--cc-text-muted)'],
            ['Environment', form.environment, 'var(--cc-blue)'],
          ].map(([label, value, color]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 10px', marginBottom: 4, background: 'var(--cc-bg-primary)', borderRadius: 4, border: '1px solid var(--cc-border)', fontSize: 12 }}>
              <span style={{ color: 'var(--cc-text-secondary)' }}>{label}</span>
              <span style={{ fontFamily: 'var(--cc-font-mono)', fontSize: 11, color }}>{value}</span>
            </div>
          ))}

          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cc-text-muted)', textTransform: 'uppercase', marginBottom: 10, marginTop: 16 }}>Maintenance Mode</div>
          <div style={{ padding: 12, background: 'var(--cc-bg-primary)', border: '1px solid var(--cc-border)', borderRadius: 6 }}>
            <div style={{ fontSize: 12, color: 'var(--cc-text-secondary)', marginBottom: 8 }}>
              Current: <span style={{ color: form.maintenance_mode ? 'var(--cc-red)' : 'var(--cc-green)', fontWeight: 700 }}>{form.maintenance_mode ? 'ENABLED' : 'DISABLED'}</span>
            </div>
            {maintenanceConfirm && (
              <div style={{ padding: '8px 10px', background: 'rgba(248,81,73,0.1)', border: '1px solid var(--cc-red)', borderRadius: 4, marginBottom: 8, fontSize: 11, color: 'var(--cc-red)' }}>
                ⚠ Are you sure? This will affect all connected users.
              </div>
            )}
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="cc-btn" style={{ fontSize: 11, borderColor: form.maintenance_mode ? 'var(--cc-green)' : 'var(--cc-red)', color: form.maintenance_mode ? 'var(--cc-green)' : 'var(--cc-red)' }} onClick={handleMaintenance}>
                {form.maintenance_mode ? 'Disable Maintenance' : maintenanceConfirm ? 'Confirm Enable' : 'Enable Maintenance'}
              </button>
              {maintenanceConfirm && <button className="cc-btn" onClick={() => setMaintenanceConfirm(false)}>Cancel</button>}
            </div>
          </div>
        </div>
      </div>
      <SaveBar onSave={handleSave} onReset={() => setForm({ ...systemSettings })} saving={saving} saved={saved} error={error} />
    </div>
  );
}

// ─── Navigation sections ──────────────────────────────────────────────────────
const SECTIONS = [
  { id: 'event', label: 'Event Settings', icon: 'bi-calendar-event', Panel: EventSettingsPanel },
  { id: 'zones', label: 'Zone Settings', icon: 'bi-hexagon', Panel: ZoneSettingsPanel },
  { id: 'cameras', label: 'Camera Settings', icon: 'bi-camera-video', Panel: CameraSettingsPanel },
  { id: 'alerts', label: 'Alert Thresholds', icon: 'bi-sliders', Panel: AlertThresholdsPanel },
  { id: 'users', label: 'User Roles', icon: 'bi-people', Panel: UserRolesPanel },
  { id: 'notifications', label: 'Notifications', icon: 'bi-bell', Panel: NotificationsPanel },
  { id: 'ai', label: 'AI Configuration', icon: 'bi-cpu', Panel: AIConfigPanel },
  { id: 'frs', label: 'FRS Configuration', icon: 'bi-person-bounding-box', Panel: FRSConfigPanel },
  { id: 'system', label: 'System Settings', icon: 'bi-gear', Panel: SystemSettingsPanel },
];

// ─── Main Settings Page ───────────────────────────────────────────────────────
export default function Settings() {
  const [activeSection, setActiveSection] = useState('event');
  const ActivePanel = SECTIONS.find(s => s.id === activeSection)?.Panel;

  return (
    <div className="cc-page">
      <div className="cc-page-header">
        <div>
          <div className="cc-page-title">Settings</div>
          <div className="cc-page-subtitle">Platform configuration  BYC AI Command Center</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 12, flex: 1 }}>
        {/* Left navigation */}
        <div className="cc-card" style={{ padding: 0, overflow: 'hidden', height: 'fit-content', position: 'sticky', top: 16 }}>
          {SECTIONS.map(s => (
            <button key={s.id} onClick={() => setActiveSection(s.id)}
              style={{
                width: '100%', padding: '10px 14px',
                background: activeSection === s.id ? 'var(--cc-accent-dim)' : 'transparent',
                border: 'none', borderLeft: `2px solid ${activeSection === s.id ? 'var(--cc-accent)' : 'transparent'}`,
                color: activeSection === s.id ? 'var(--cc-blue)' : 'var(--cc-text-secondary)',
                display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, cursor: 'pointer', textAlign: 'left',
                transition: 'all 0.15s',
              }}
            >
              <i className={`bi ${s.icon}`} style={{ fontSize: 14, width: 18, textAlign: 'center' }} />
              {s.label}
            </button>
          ))}
        </div>
        {/* Right panel */}
        <div className="cc-card">
          {ActivePanel && <ActivePanel />}
        </div>
      </div>
    </div>
  );
}
