import { useEffect, useState } from 'react';
import api from '../services/api';

const mb = n => (Number(n || 0) / 1024 / 1024).toFixed(2) + ' MB';
const gb = n => (Number(n || 0) / 1024 / 1024 / 1024).toFixed(2) + ' GB';

export default function Admin() {
  const [data, setData] = useState({ stats: {}, processes: [], logs: [] });
  const [report, setReport] = useState([]);
  const [corrupt, setCorrupt] = useState([]);
  const [resources, setResources] = useState(null);
  const [users, setUsers] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditAction, setAuditAction] = useState('');
  const [msg, setMsg] = useState('');

  async function load() {
    try {
      const [d, r, c, m, u, l] = await Promise.all([
        api.get('/admin/dashboard'), api.get('/admin/storage-report'), api.get('/admin/corrupted'),
        api.get('/admin/resource-monitor'), api.get('/admin/users'), api.get('/admin/audit-logs', { params: { action: auditAction, limit: 100 } })
      ]);
      setData(d.data); setReport(r.data.report || []); setCorrupt(c.data.files || []);
      setResources(m.data); setUsers(u.data.users || []); setAuditLogs(l.data.logs || []);
    } catch (e) { setMsg(e.response?.data?.error || 'Could not load admin data. Check admin login and Flask terminal.'); }
  }
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [auditAction]);

  async function scheduler() { try { const r = await api.post('/admin/simulate-scheduler'); setMsg(`${r.data.message}: ${(r.data.pids || []).join(', ')}`); load(); } catch (e) { setMsg(e.response?.data?.error || 'Scheduler action failed'); } }
  async function tick() { try { const r = await api.post('/admin/scheduler/tick'); setMsg(r.data.pid ? `Round Robin tick: ${r.data.pid} → ${r.data.state}, remaining ${r.data.remaining_time}` : r.data.message); load(); } catch (e) { setMsg(e.response?.data?.error || 'Scheduler tick failed'); } }
  async function failure() { try { const r = await api.post('/admin/simulate-failure'); setMsg(r.data.message); load(); } catch (e) { setMsg(e.response?.data?.error || 'Failure simulation failed'); } }
  async function recover(id) { try { const r = await api.post('/admin/recover/' + id); setMsg(r.data.message); load(); } catch (e) { setMsg(e.response?.data?.error || 'Recovery failed'); } }

  async function updateUser(user, changes) {
    try { const r = await api.patch(`/admin/users/${user.id}`, changes); setMsg(r.data.message); await load(); }
    catch (e) { setMsg(e.response?.data?.error || 'Could not update user'); }
  }
  async function changeQuota(user) {
    const currentGB = (Number(user.storage_quota) / 1024 ** 3).toFixed(2);
    const entered = prompt(`Enter new storage quota in GB for ${user.email}:`, currentGB);
    if (entered === null) return;
    const value = Number(entered);
    if (!Number.isFinite(value) || value < 0) { setMsg('Enter a valid non-negative number of GB'); return; }
    await updateUser(user, { storage_quota: Math.round(value * 1024 ** 3) });
  }

  return <main className="page">
    <div className="hero"><div><h1>Admin / System Control</h1><p>DBMS + OS monitoring, security audit and user management</p></div><div className="actions"><button onClick={scheduler}>Create 5 Scheduler Jobs</button><button onClick={tick}>Run RR Quantum</button><button className="danger" onClick={failure}>Simulate Storage Failure</button></div></div>
    {msg && <div className="notice">{msg}</div>}

    <section className="stats"><div><b>{data.stats.users || 0}</b><span>Users</span></div><div><b>{data.stats.files || 0}</b><span>Active Files</span></div><div><b>{data.stats.successful_backups || 0}</b><span>Successful Backups</span></div></section>

    <section className="card"><h2>System Resource Monitoring</h2>
      {!resources ? <p>Loading resource information...</p> : <>
        <div className="stats">
          <div><b>{resources.disk?.percent_used ?? 0}%</b><span>Host disk used</span><small>{gb(resources.disk?.free_bytes)} free</small></div>
          <div><b>{mb(resources.backup_folder_bytes)}</b><span>Backup files on disk</span><small>Local backup directory</small></div>
          <div><b>{resources.active_processes ?? 0}</b><span>Active simulated processes</span><small>{resources.failed_processes ?? 0} failed</small></div>
        </div>
        <p><b>Primary storage:</b> {resources.primary_storage_path}</p><p><b>Backup storage:</b> {resources.backup_storage_path}</p>
        <h3>Process state counts</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>{Object.entries(resources.process_counts || {}).map(([state, count]) => <span className="pill" key={state}>{state}: {count}</span>)}</div>
        <small>Disk usage is the host disk's usage, not just CloudVault's files. Process counts are the app's simulated OS jobs, not all Windows processes.</small>
      </>}
    </section>

    <section className="card"><h2>OS Process Monitor</h2><div style={{ overflowX: 'auto' }}><table><thead><tr><th>PID</th><th>Operation</th><th>State</th><th>Priority</th><th>Burst</th><th>Remaining</th></tr></thead><tbody>{(data.processes || []).map(p => <tr key={p.pid}><td>{p.pid}</td><td>{p.operation}</td><td><span className={'pill ' + p.state.toLowerCase()}>{p.state}</span></td><td>{p.priority}</td><td>{p.burst_time}</td><td>{p.remaining_time}</td></tr>)}</tbody></table></div></section>

    <section className="card"><h2>User Management & Quotas</h2><p>Admins can activate/suspend accounts, change roles, and adjust storage quota.</p><div style={{ overflowX: 'auto' }}><table><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Used / Quota</th><th>Actions</th></tr></thead><tbody>{users.map(u => <tr key={u.id}>
      <td>{u.name}<br /><small>{u.email}</small></td>
      <td><select value={u.role} onChange={e => updateUser(u, { role: e.target.value })}><option value="MEMBER">MEMBER</option><option value="ADMIN">ADMIN</option></select></td>
      <td><span className="pill">{u.status}</span></td>
      <td>{gb(u.storage_used)} / {gb(u.storage_quota)}</td>
      <td><div className="actions"><button onClick={() => changeQuota(u)}>Change quota</button><button disabled={u.id === JSON.parse(localStorage.getItem('user') || 'null')?.id} onClick={() => updateUser(u, { status: u.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' })}>{u.status === 'ACTIVE' ? 'Suspend' : 'Activate'}</button></div></td>
    </tr>)}</tbody></table></div></section>

    <section className="card"><h2>User Storage Report</h2><div style={{ overflowX: 'auto' }}><table><thead><tr><th>User</th><th>Email</th><th>Files</th><th>Used</th><th>Quota</th></tr></thead><tbody>{report.map(r => <tr key={r.id}><td>{r.name}</td><td>{r.email}</td><td>{r.file_count}</td><td>{mb(r.used_bytes)}</td><td>{gb(r.storage_quota)}</td></tr>)}</tbody></table></div></section>

    <section className="card"><h2>Disaster Recovery</h2>{corrupt.map(f => <div className="version" key={f.id}><span>⚠ {f.filename} is CORRUPTED</span><button onClick={() => recover(f.id)}>Recover from latest backup</button></div>)}{corrupt.length === 0 && <p>No corrupted files. Use “Simulate Storage Failure” above to test recovery.</p>}</section>

    <section className="card"><h2>Audit Logs & Security Monitoring</h2><p>Login attempts and file/user/admin actions are recorded here. Passwords are never logged.</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}><input value={auditAction} onChange={e => setAuditAction(e.target.value)} placeholder="Filter action e.g. LOGIN" style={{ padding: 10, border: '1px solid #d0d5dd', borderRadius: 8, minWidth: 220 }} /><button onClick={load}>Refresh logs</button><button onClick={() => setAuditAction('')}>Clear filter</button></div>
      {auditLogs.length === 0 ? <p>No audit events match this filter.</p> : <div style={{ overflowX: 'auto' }}><table><thead><tr><th>Time</th><th>User / Email</th><th>Action</th><th>Details</th></tr></thead><tbody>{auditLogs.map(l => <tr key={l.id}><td>{new Date(l.created_at).toLocaleString()}</td><td>{l.email}</td><td><span className="pill">{l.action}</span></td><td>{l.details}</td></tr>)}</tbody></table></div>}
    </section>
  </main>;
}
