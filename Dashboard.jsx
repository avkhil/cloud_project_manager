import { useEffect, useState } from 'react';
import api from '../services/api';

const mb = n => (Number(n || 0) / 1024 / 1024).toFixed(2) + ' MB';
const gb = n => (Number(n || 0) / 1024 / 1024 / 1024).toFixed(2) + ' GB';

export default function Dashboard() {
  const [files, setFiles] = useState([]);
  const [folders, setFolders] = useState([]);
  const [selected, setSelected] = useState(null);
  const [versions, setVersions] = useState([]);
  const [trash, setTrash] = useState([]);
  const [storage, setStorage] = useState({ used_bytes: 0, quota_bytes: 0, free_bytes: 0, percent_used: 0 });
  const [search, setSearch] = useState('');
  const [fileType, setFileType] = useState('all');
  const [sort, setSort] = useState('newest');
  const [message, setMessage] = useState('');
  const [showTrash, setShowTrash] = useState(false);

  async function loadFiles() {
    try {
      const params = { q: search, type: fileType, sort };
      if (selected !== null) params.folder_id = selected;
      const [f, fo, s, t] = await Promise.all([
        api.get('/files', { params }), api.get('/folders'), api.get('/files/storage'), api.get('/files/trash')
      ]);
      setFiles(f.data.files || []);
      setFolders(fo.data.folders || []);
      setStorage(s.data || {});
      setTrash(t.data.files || []);
    } catch (e) {
      setMessage(e.response?.data?.error || 'Could not load files. Check that you are logged in and Flask is running.');
    }
  }

  useEffect(() => { loadFiles(); }, [selected, search, fileType, sort]);

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    if (selected !== null) fd.append('folder_id', selected);
    try {
      const r = await api.post('/files/upload', fd);
      setMessage(`${r.data.message} | Process ${r.data.pid}`);
      await loadFiles();
    } catch (x) { setMessage(x.response?.data?.error || 'Upload failed'); }
    e.target.value = '';
  }

  async function download(id, name) {
    try {
      const r = await api.get(`/files/${id}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a'); a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setMessage(e.response?.data?.error || 'Download failed'); }
  }

  async function moveToTrash(id) {
    if (!confirm('Move this file to the recycle bin?')) return;
    try { const r = await api.delete('/files/' + id); setMessage(r.data.message); await loadFiles(); }
    catch (e) { setMessage(e.response?.data?.error || 'Could not delete file'); }
  }

  async function recoverFromTrash(id) {
    try { const r = await api.post(`/files/${id}/recover-deleted`); setMessage(r.data.message); setShowTrash(false); await loadFiles(); }
    catch (e) { setMessage(e.response?.data?.error || 'Recovery failed'); }
  }

  async function permanentDelete(id) {
    if (!confirm('Permanently delete this file and its stored versions/backups? This cannot be undone.')) return;
    try { const r = await api.delete(`/files/${id}/permanent`); setMessage(r.data.message); await loadFiles(); }
    catch (e) { setMessage(e.response?.data?.error || 'Permanent deletion failed'); }
  }

  async function showVersions(id) {
    try { const r = await api.get(`/files/${id}/versions`); setVersions(r.data.versions || []); setMessage('Select a version to restore.'); }
    catch (e) { setMessage(e.response?.data?.error || 'Could not load versions'); }
  }

  async function restoreVersion(fid, vid) {
    try { const r = await api.post(`/files/${fid}/restore/${vid}`); setMessage(`${r.data.message}${r.data.pid ? ' | ' + r.data.pid : ''}`); await loadFiles(); }
    catch (e) { setMessage(e.response?.data?.error || 'Version restore failed'); }
  }

  async function createFolder() {
    const name = prompt('Folder name');
    if (!name?.trim()) return;
    try { await api.post('/folders', { name: name.trim() }); setMessage('Folder created'); await loadFiles(); }
    catch (e) { setMessage(e.response?.data?.error || 'Could not create folder'); }
  }

  return <main className="page">
    <header className="hero">
      <div><h1>My Cloud</h1><p>Store files. Protect them. Recover them.</p></div>
      <label className="upload"><input type="file" onChange={upload} /><b>+ Upload</b></label>
    </header>
    {message && <div className="notice">{message}</div>}

    <section className="card">
      <h2>Storage Usage</h2>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <span><b>{gb(storage.used_bytes)}</b> used</span><span>{gb(storage.free_bytes)} free</span><span>{gb(storage.quota_bytes)} total quota</span>
      </div>
      <div style={{ height: 12, background: '#e4e7ec', borderRadius: 99, overflow: 'hidden', marginTop: 12 }}>
        <div style={{ height: '100%', width: `${Math.min(100, Number(storage.percent_used || 0))}%`, background: Number(storage.percent_used) >= 90 ? '#b42318' : '#1f5eff' }} />
      </div>
      <small>{Number(storage.percent_used || 0).toFixed(1)}% used. Deleted files in the recycle bin do not count toward active storage.</small>
    </section>

    <section className="grid">
      <div className="card">
        <h2>Folders</h2>
        <div className="folderrow">
          <button onClick={() => setSelected(null)} className={selected === null ? 'selected' : ''}>All files</button>
          {folders.map(f => <button key={f.id} onClick={() => setSelected(f.id)} className={selected === f.id ? 'selected' : ''}>📁 {f.name}</button>)}
        </div>
        <button onClick={createFolder}>+ New Folder</button>
        <hr style={{ border: 0, borderTop: '1px solid #eee', margin: '18px 0' }} />
        <button onClick={() => setShowTrash(v => !v)}>{showTrash ? '← Back to files' : `♻ Recycle Bin (${trash.length})`}</button>
      </div>

      <div className="card files">
        {showTrash ? <>
          <h2>Recycle Bin</h2>
          <p>Restore a deleted file or permanently remove it.</p>
          {trash.length === 0 ? <p>Recycle bin is empty.</p> : trash.map(f => <article className="file" key={f.id}>
            <div><strong>🗑 {f.filename}</strong><small>{mb(f.size_bytes)} · Deleted file</small></div>
            <div className="actions"><button onClick={() => recoverFromTrash(f.id)}>Restore</button><button className="danger" onClick={() => permanentDelete(f.id)}>Delete forever</button></div>
          </article>)}
        </> : <>
          <h2>Files</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <input aria-label="Search files" placeholder="Search filename..." value={search} onChange={e => setSearch(e.target.value)} style={{ flex: '1 1 180px', minWidth: 150, padding: 10, border: '1px solid #d0d5dd', borderRadius: 8 }} />
            <select aria-label="Filter by type" value={fileType} onChange={e => setFileType(e.target.value)} style={{ padding: 9, borderRadius: 8, border: '1px solid #d0d5dd' }}>
              <option value="all">All types</option><option value="pdf">PDF</option><option value="docx">DOCX</option><option value="doc">DOC</option><option value="txt">TXT</option><option value="png">PNG</option><option value="jpg">JPG</option><option value="jpeg">JPEG</option><option value="zip">ZIP</option><option value="xlsx">XLSX</option>
            </select>
            <select aria-label="Sort files" value={sort} onChange={e => setSort(e.target.value)} style={{ padding: 9, borderRadius: 8, border: '1px solid #d0d5dd' }}>
              <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Name A–Z</option><option value="size">Largest first</option>
            </select>
          </div>
          {files.length === 0 ? <p>No matching files. Upload a file or change your search.</p> : files.map(f => <article className="file" key={f.id}>
            <div><strong>📄 {f.filename}</strong><small>{mb(f.size_bytes)} · v{f.current_version} · {f.status}</small></div>
            <div className="actions"><button onClick={() => download(f.id, f.filename)}>Download</button><button onClick={() => showVersions(f.id)}>Versions</button><button onClick={() => moveToTrash(f.id)}>Delete</button></div>
          </article>)}
        </>}
      </div>
    </section>

    {versions.length > 0 && <section className="card"><h2>Version History</h2>{versions.map(v => <div className="version" key={v.id}><span>Version {v.version_number} · {mb(v.size_bytes)} · {v.created_at ? new Date(v.created_at).toLocaleString() : ''}</span><button onClick={() => restoreVersion(v.file_id, v.id)}>Restore version</button></div>)}</section>}
  </main>;
}
