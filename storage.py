import hashlib, os, shutil
from pathlib import Path
from flask import current_app
from werkzeug.utils import secure_filename
from app import db
from app.models import FileVersion, Backup

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def user_dir(base, user_id):
    p = Path(base) / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

def save_primary(file_storage, user_id, file_id, version):
    filename = secure_filename(file_storage.filename) or f'file_{file_id}'
    folder = user_dir(current_app.config['PRIMARY_STORAGE'], user_id)
    path = folder / f'{file_id}_v{version}_{filename}'
    file_storage.save(path)
    return str(path), filename

def copy_backup(source_path, user_id, file_id, version):
    folder = user_dir(current_app.config['BACKUP_STORAGE'], user_id)
    dest = folder / f'{file_id}_v{version}_backup'
    shutil.copy2(source_path, dest)
    return str(dest)

def create_version_and_backup(file_obj, user_id, source_path, version, size):
    checksum = sha256(source_path)
    fv = FileVersion(file_id=file_obj.id, version_number=version, size_bytes=size,
                     storage_path=source_path, checksum=checksum)
    db.session.add(fv); db.session.flush()
    backup_path = copy_backup(source_path, user_id, file_obj.id, version)
    b = Backup(file_id=file_obj.id, version_id=fv.id, backup_path=backup_path,
               size_bytes=size, checksum=checksum, status='SUCCESS')
    db.session.add(b)
    return fv, b
