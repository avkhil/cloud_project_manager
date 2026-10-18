import os
import shutil
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import text
from app import db
from app.models import User, File, Backup, Process, ActivityLog
from app.routes.common import admin_required

admin_bp = Blueprint('admin', __name__)


def write_admin_log(admin, action, details):
    db.session.add(ActivityLog(user_id=admin.id, action=action, details=details[:500]))


@admin_bp.get('/dashboard')
@admin_required
def dashboard(admin):
    users = User.query.count()
    files = File.query.filter_by(status='ACTIVE').count()
    backups = Backup.query.filter_by(status='SUCCESS').count()
    processes = Process.query.order_by(Process.created_at.desc()).limit(30).all()
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(30).all()
    return jsonify({
        'stats': {'users': users, 'files': files, 'successful_backups': backups},
        'processes': [{'pid': p.pid, 'operation': p.operation, 'state': p.state,
                       'priority': p.priority, 'burst_time': p.burst_time,
                       'remaining_time': p.remaining_time, 'created_at': p.created_at.isoformat()} for p in processes],
        'logs': [{'user_id': l.user_id, 'action': l.action, 'details': l.details,
                  'created_at': l.created_at.isoformat()} for l in logs]
    })


@admin_bp.get('/storage-report')
@admin_required
def storage_report(admin):
    rows = db.session.execute(text('SELECT * FROM user_storage_report ORDER BY used_bytes DESC')).mappings().all()
    return jsonify({'report': [dict(r) for r in rows]})


@admin_bp.get('/resource-monitor')
@admin_required
def resource_monitor(admin):
    primary = current_app.config['PRIMARY_STORAGE']
    backup = current_app.config['BACKUP_STORAGE']
    p_usage = shutil.disk_usage(primary)
    b_usage = shutil.disk_usage(backup)
    states = db.session.query(Process.state, db.func.count(Process.id)).group_by(Process.state).all()
    process_counts = {state: count for state, count in states}
    return jsonify({
        'disk': {'total_bytes': p_usage.total, 'used_bytes': p_usage.used,
                 'free_bytes': p_usage.free, 'percent_used': round(p_usage.used / p_usage.total * 100, 2) if p_usage.total else 0},
        'primary_storage_path': primary,
        'backup_storage_path': backup,
        'backup_folder_bytes': sum(os.path.getsize(os.path.join(root, name)) for root, _, names in os.walk(backup) for name in names if os.path.isfile(os.path.join(root, name))),
        'process_counts': process_counts,
        'active_processes': Process.query.filter(Process.state.in_(['READY', 'RUNNING', 'WAITING'])).count(),
        'failed_processes': Process.query.filter_by(state='FAILED').count(),
    })


@admin_bp.get('/audit-logs')
@admin_required
def audit_logs(admin):
    q = ActivityLog.query
    action = request.args.get('action', '').strip()
    user_id = request.args.get('user_id', type=int)
    limit = min(max(request.args.get('limit', 100, type=int), 1), 500)
    if action:
        q = q.filter(ActivityLog.action.ilike(f'%{action}%'))
    if user_id:
        q = q.filter_by(user_id=user_id)
    rows = q.order_by(ActivityLog.created_at.desc()).limit(limit).all()
    user_ids = {r.user_id for r in rows if r.user_id is not None}
    users = {u.id: u.email for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return jsonify({'logs': [{'id': r.id, 'user_id': r.user_id,
                              'email': users.get(r.user_id, 'System / deleted user'),
                              'action': r.action, 'details': r.details,
                              'created_at': r.created_at.isoformat()} for r in rows]})


@admin_bp.get('/users')
@admin_required
def list_users(admin):
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'users': [{'id': u.id, 'name': u.name, 'email': u.email,
                              'role': u.role, 'status': u.status,
                              'storage_quota': int(u.storage_quota or 0),
                              'storage_used': int(u.storage_used or 0),
                              'created_at': u.created_at.isoformat() if u.created_at else None}
                             for u in users]})


@admin_bp.patch('/users/<int:user_id>')
@admin_required
def update_user(admin, user_id):
    u = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    changes = []
    if 'status' in data:
        status = str(data['status']).upper()
        if status not in ('ACTIVE', 'DISABLED'):
            return jsonify({'error': 'status must be ACTIVE or DISABLED'}), 400
        if u.id == admin.id and status != 'ACTIVE':
            return jsonify({'error': 'You cannot disable your own account'}), 400
        if u.status != status:
            u.status = status
            changes.append(f'status={status}')
    if 'role' in data:
        role = str(data['role']).upper()
        if role not in ('ADMIN', 'MEMBER'):
            return jsonify({'error': 'role must be ADMIN or MEMBER'}), 400
        if u.id == admin.id and role != 'ADMIN':
            return jsonify({'error': 'You cannot remove your own admin role'}), 400
        if u.role != role:
            u.role = role
            changes.append(f'role={role}')
    if 'storage_quota' in data:
        try:
            quota = int(data['storage_quota'])
            if quota < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({'error': 'storage_quota must be a non-negative integer number of bytes'}), 400
        if quota < int(u.storage_used or 0):
            return jsonify({'error': 'Quota cannot be lower than current storage used'}), 400
        if u.storage_quota != quota:
            u.storage_quota = quota
            changes.append(f'storage_quota={quota}')
    if changes:
        write_admin_log(admin, 'USER_UPDATED', f'Updated {u.email}: {", ".join(changes)}')
        db.session.commit()
    return jsonify({'message': 'User updated' if changes else 'No changes made',
                    'user': {'id': u.id, 'name': u.name, 'email': u.email,
                             'role': u.role, 'status': u.status,
                             'storage_quota': int(u.storage_quota or 0),
                             'storage_used': int(u.storage_used or 0)}})


@admin_bp.post('/simulate-scheduler')
@admin_required
def simulate_scheduler(admin):
    from app.services.process_manager import process_manager
    created = []
    for i in range(5):
        p = process_manager.create(admin.id, f'SCHEDULED_JOB_{i+1}', burst_time=3+i, priority=i+1)
        process_manager.run(p)
        created.append(p.pid)
    write_admin_log(admin, 'SCHEDULER_SIMULATED', 'Created 5 scheduler jobs')
    db.session.commit()
    return jsonify({'message': 'Created 5 scheduler jobs', 'pids': created})


@admin_bp.post('/scheduler/tick')
@admin_required
def scheduler_tick(admin):
    from datetime import datetime
    ready = Process.query.filter(Process.state.in_(['READY', 'RUNNING', 'WAITING'])).order_by(Process.created_at.asc()).all()
    if not ready:
        return jsonify({'message': 'No active jobs'})
    p = ready[0]
    if p.state in ('WAITING', 'READY'):
        p.state = 'RUNNING'
        p.started_at = p.started_at or datetime.utcnow()
    p.remaining_time = max(0, p.remaining_time - 2)
    if p.remaining_time == 0:
        p.state = 'TERMINATED'
        p.completed_at = datetime.utcnow()
    else:
        p.state = 'READY'
    write_admin_log(admin, 'SCHEDULER_TICK', f'{p.pid} -> {p.state}; remaining={p.remaining_time}')
    db.session.commit()
    return jsonify({'pid': p.pid, 'state': p.state, 'remaining_time': p.remaining_time, 'quantum': 2})


@admin_bp.get('/corrupted')
@admin_required
def corrupted(admin):
    rows = File.query.filter_by(status='CORRUPTED').all()
    return jsonify({'files': [{'id': f.id, 'filename': f.filename} for f in rows]})


@admin_bp.post('/simulate-failure')
@admin_required
def simulate_failure(admin):
    f = File.query.filter_by(status='ACTIVE').first()
    if not f:
        return jsonify({'error': 'No active file available'}), 404
    f.status = 'CORRUPTED'
    write_admin_log(admin, 'STORAGE_FAILURE_SIMULATED', f'Simulated failure for {f.filename}')
    db.session.commit()
    return jsonify({'message': f'Simulated failure for {f.filename}', 'file_id': f.id})


@admin_bp.post('/recover/<int:file_id>')
@admin_required
def recover(admin, file_id):
    f = File.query.get_or_404(file_id)
    b = Backup.query.filter_by(file_id=file_id, status='SUCCESS').order_by(Backup.created_at.desc()).first()
    if not b or not os.path.isfile(b.backup_path):
        return jsonify({'error': 'No accessible successful backup'}), 404
    try:
        os.makedirs(os.path.dirname(f.storage_path), exist_ok=True)
        shutil.copy2(b.backup_path, f.storage_path)
        f.status = 'ACTIVE'
        write_admin_log(admin, 'DISASTER_RECOVERY', f'Recovered {f.filename} from backup #{b.id}')
        db.session.commit()
        return jsonify({'message': f'Recovered {f.filename} from backup'})
    except OSError:
        db.session.rollback()
        current_app.logger.exception('Disaster recovery failed')
        return jsonify({'error': 'Recovery failed. Check the Flask terminal.'}), 500


@admin_bp.post('/users/<int:user_id>/toggle')
@admin_required
def toggle_user(admin, user_id):
    u = User.query.get_or_404(user_id)
    if u.id == admin.id:
        return jsonify({'error': 'You cannot disable your own account'}), 400
    u.status = 'DISABLED' if u.status == 'ACTIVE' else 'ACTIVE'
    write_admin_log(admin, 'USER_STATUS_CHANGED', f'{u.email} status changed to {u.status}')
    db.session.commit()
    return jsonify({'status': u.status})
