import os
import shutil
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, current_app
from app import db
from app.models import User, File, FileVersion, Backup, ActivityLog
from app.routes.common import auth_required
from app.services.storage import save_primary, create_version_and_backup
from app.services.process_manager import process_manager

files_bp = Blueprint('files', __name__)


def serialize_file(f):
    return {
        'id': f.id, 'filename': f.filename, 'size_bytes': f.size_bytes,
        'current_version': f.current_version, 'status': f.status,
        'folder_id': f.folder_id, 'mime_type': f.mime_type,
        'created_at': f.created_at.isoformat() if f.created_at else None,
        'updated_at': f.updated_at.isoformat() if f.updated_at else None,
    }


def log_action(user_id, action, details):
    db.session.add(ActivityLog(user_id=user_id, action=action, details=details[:500]))


@files_bp.get('')
@auth_required
def list_files(user):
    """List active files, optionally searching/filtering/sorting them."""
    q = File.query.filter_by(user_id=user.id, status='ACTIVE')
    folder_id = request.args.get('folder_id', type=int)
    search = request.args.get('q', '').strip()
    file_type = request.args.get('type', '').strip().lower()
    sort = request.args.get('sort', 'newest')

    if folder_id is not None:
        q = q.filter_by(folder_id=folder_id)
    if search:
        q = q.filter(File.filename.ilike(f'%{search}%'))
    if file_type and file_type != 'all':
        ext = file_type.lstrip('.')
        q = q.filter(db.func.lower(File.filename).like(f'%.{ext}'))

    sort_columns = {
        'name': File.filename.asc(),
        'size': File.size_bytes.desc(),
        'oldest': File.created_at.asc(),
        'newest': File.updated_at.desc(),
    }
    q = q.order_by(sort_columns.get(sort, File.updated_at.desc()))
    return jsonify({'files': [serialize_file(f) for f in q.all()]})


@files_bp.get('/storage')
@auth_required
def storage_usage(user):
    used = db.session.query(db.func.coalesce(db.func.sum(File.size_bytes), 0)).filter_by(user_id=user.id, status='ACTIVE').scalar() or 0
    quota = int(user.storage_quota or 0)
    user.storage_used = int(used)
    db.session.commit()
    return jsonify({'used_bytes': int(used), 'quota_bytes': quota,
                    'free_bytes': max(0, quota - int(used)),
                    'percent_used': round((int(used) / quota) * 100, 2) if quota else 0})


@files_bp.get('/trash')
@auth_required
def list_trash(user):
    rows = File.query.filter_by(user_id=user.id, status='DELETED').order_by(File.updated_at.desc()).all()
    return jsonify({'files': [serialize_file(f) for f in rows]})


@files_bp.post('/<int:file_id>/recover-deleted')
@auth_required
def recover_deleted(user, file_id):
    f = File.query.filter_by(id=file_id, user_id=user.id, status='DELETED').first_or_404()
    used = db.session.query(db.func.coalesce(db.func.sum(File.size_bytes), 0)).filter_by(user_id=user.id, status='ACTIVE').scalar() or 0
    if int(used) + int(f.size_bytes) > int(user.storage_quota):
        return jsonify({'error': 'Not enough storage quota to restore this file. Delete another file or ask the admin to increase your quota.'}), 400
    if not os.path.isfile(f.storage_path):
        return jsonify({'error': 'The original file is missing from primary storage. Ask the admin to recover it from backup.'}), 404
    f.status = 'ACTIVE'
    user.storage_used = int(used) + int(f.size_bytes)
    log_action(user.id, 'FILE_RECOVERED_FROM_TRASH', f'Restored {f.filename} from recycle bin')
    db.session.commit()
    return jsonify({'message': f'{f.filename} restored from recycle bin'})


@files_bp.delete('/<int:file_id>/permanent')
@auth_required
def permanently_delete(user, file_id):
    f = File.query.filter_by(id=file_id, user_id=user.id, status='DELETED').first_or_404()
    paths = [f.storage_path]
    paths += [v.storage_path for v in FileVersion.query.filter_by(file_id=f.id).all()]
    paths += [b.backup_path for b in Backup.query.filter_by(file_id=f.id).all()]
    # Only delete files inside this application's configured storage folders.
    allowed_roots = [Path(current_app.config['PRIMARY_STORAGE']).resolve(), Path(current_app.config['BACKUP_STORAGE']).resolve()]
    for raw_path in set(paths):
        if not raw_path:
            continue
        try:
            candidate = Path(raw_path).resolve()
            if any(candidate == root or root in candidate.parents for root in allowed_roots) and candidate.is_file():
                candidate.unlink()
        except OSError:
            current_app.logger.exception('Could not remove stored file during permanent deletion')
    filename = f.filename
    log_action(user.id, 'FILE_PERMANENTLY_DELETED', f'Permanently deleted {filename}')
    db.session.delete(f)
    db.session.commit()
    return jsonify({'message': f'{filename} permanently deleted'})


@files_bp.post('/upload')
@auth_required
def upload(user):
    upload = request.files.get('file')
    folder_id = request.form.get('folder_id', type=int)
    if not upload or not upload.filename:
        return jsonify({'error': 'Choose a file'}), 400
    if folder_id is not None:
        from app.models import Folder
        if not Folder.query.filter_by(id=folder_id, user_id=user.id).first():
            return jsonify({'error': 'Invalid folder'}), 400
    upload.stream.seek(0, 2)
    size = upload.stream.tell()
    upload.stream.seek(0)
    used = db.session.query(db.func.coalesce(db.func.sum(File.size_bytes), 0)).filter_by(user_id=user.id, status='ACTIVE').scalar() or 0
    if int(used) + size > int(user.storage_quota):
        return jsonify({'error': 'Storage quota exceeded'}), 400

    f = File(user_id=user.id, folder_id=folder_id, filename=upload.filename,
             current_version=1, size_bytes=size, storage_path='', mime_type=upload.mimetype)
    db.session.add(f)
    db.session.flush()
    process = process_manager.create(user.id, 'UPLOAD', 3)
    process_manager.run(process)
    try:
        path, safe_name = save_primary(upload, user.id, f.id, 1)
        f.filename = safe_name
        f.storage_path = path
        create_version_and_backup(f, user.id, path, 1, size)
        user.storage_used = int(used) + size
        log_action(user.id, 'UPLOAD', f'Uploaded {f.filename}')
        db.session.commit()
        process_manager.finish(process)
        return jsonify({'message': 'Upload and backup successful', 'file': serialize_file(f), 'pid': process.pid}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('File upload failed')
        return jsonify({'error': 'Upload failed. Check the Flask terminal for details.'}), 500


@files_bp.get('/<int:file_id>/download')
@auth_required
def download(user, file_id):
    f = File.query.filter_by(id=file_id, user_id=user.id, status='ACTIVE').first_or_404()
    if not os.path.isfile(f.storage_path):
        return jsonify({'error': 'File is missing from primary storage'}), 404
    log_action(user.id, 'DOWNLOAD', f'Downloaded {f.filename}')
    db.session.commit()
    return send_file(f.storage_path, as_attachment=True, download_name=f.filename)


@files_bp.delete('/<int:file_id>')
@auth_required
def delete_file(user, file_id):
    f = File.query.filter_by(id=file_id, user_id=user.id, status='ACTIVE').first_or_404()
    f.status = 'DELETED'
    user.storage_used = max(0, int(user.storage_used or 0) - int(f.size_bytes or 0))
    log_action(user.id, 'DELETE_TO_TRASH', f'Moved {f.filename} to recycle bin')
    db.session.commit()
    return jsonify({'message': 'File moved to recycle bin'})


@files_bp.get('/<int:file_id>/versions')
@auth_required
def versions(user, file_id):
    f = File.query.filter_by(id=file_id, user_id=user.id).first_or_404()
    return jsonify({'versions': [
        {'id': v.id, 'file_id': f.id, 'version_number': v.version_number,
         'size_bytes': v.size_bytes, 'created_at': v.created_at.isoformat(), 'checksum': v.checksum}
        for v in FileVersion.query.filter_by(file_id=f.id).order_by(FileVersion.version_number.desc()).all()
    ]})


@files_bp.post('/<int:file_id>/restore/<int:version_id>')
@auth_required
def restore(user, file_id, version_id):
    f = File.query.filter_by(id=file_id, user_id=user.id).first_or_404()
    v = FileVersion.query.filter_by(id=version_id, file_id=f.id).first_or_404()
    if not os.path.isfile(v.storage_path):
        return jsonify({'error': 'That version is no longer available'}), 404
    process = process_manager.create(user.id, 'RESTORE', 2)
    process_manager.run(process)
    try:
        old_size = int(f.size_bytes or 0) if f.status == 'ACTIVE' else 0
        active_used = db.session.query(db.func.coalesce(db.func.sum(File.size_bytes), 0)).filter_by(user_id=user.id, status='ACTIVE').scalar() or 0
        if f.status != 'ACTIVE' and int(active_used) + int(v.size_bytes) > int(user.storage_quota):
            return jsonify({'error': 'Storage quota exceeded'}), 400
        shutil.copy2(v.storage_path, f.storage_path)
        f.current_version = v.version_number
        f.status = 'ACTIVE'
        f.size_bytes = v.size_bytes
        user.storage_used = max(0, int(active_used) - old_size) + int(v.size_bytes)
        log_action(user.id, 'VERSION_RESTORED', f'Restored {f.filename} to v{v.version_number}')
        db.session.commit()
        process_manager.finish(process)
        return jsonify({'message': f'Restored version {v.version_number}', 'pid': process.pid})
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Version restore failed')
        return jsonify({'error': 'Restore failed. Check the Flask terminal for details.'}), 500
