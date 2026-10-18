from datetime import datetime
from app import db

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('ADMIN','MEMBER'), default='MEMBER', nullable=False)
    status = db.Column(db.Enum('ACTIVE','DISABLED'), default='ACTIVE', nullable=False)
    storage_quota = db.Column(db.BigInteger, default=1073741824, nullable=False)
    storage_used = db.Column(db.BigInteger, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Folder(db.Model):
    __tablename__ = 'folders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('folders.id', ondelete='CASCADE'))
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folders.id', ondelete='SET NULL'))
    filename = db.Column(db.String(255), nullable=False)
    current_version = db.Column(db.Integer, default=1, nullable=False)
    size_bytes = db.Column(db.BigInteger, default=0, nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(150))
    status = db.Column(db.Enum('ACTIVE','DELETED','CORRUPTED'), default='ACTIVE', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    versions = db.relationship('FileVersion', backref='file', cascade='all, delete-orphan')
    backups = db.relationship('Backup', backref='file', cascade='all, delete-orphan')

class FileVersion(db.Model):
    __tablename__ = 'file_versions'
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('files.id', ondelete='CASCADE'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    checksum = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Backup(db.Model):
    __tablename__ = 'backups'
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('files.id', ondelete='CASCADE'), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey('file_versions.id', ondelete='SET NULL'))
    backup_path = db.Column(db.String(500), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    checksum = db.Column(db.String(128))
    status = db.Column(db.Enum('PENDING','SUCCESS','FAILED'), default='PENDING', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Process(db.Model):
    __tablename__ = 'processes'
    id = db.Column(db.Integer, primary_key=True)
    pid = db.Column(db.String(30), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    operation = db.Column(db.String(100), nullable=False)
    state = db.Column(db.Enum('READY','RUNNING','WAITING','TERMINATED','FAILED'), default='READY')
    priority = db.Column(db.Integer, default=5)
    burst_time = db.Column(db.Integer, default=1)
    remaining_time = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

class ResourceEvent(db.Model):
    __tablename__ = 'resource_events'
    id = db.Column(db.Integer, primary_key=True)
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id', ondelete='SET NULL'))
    resource_name = db.Column(db.String(100), nullable=False)
    event_type = db.Column(db.Enum('ALLOCATED','RELEASED','WAITING'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
